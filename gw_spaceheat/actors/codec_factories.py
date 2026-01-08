"""Scada Codec"""


from gwproactor.config.proactor_config import ProactorName
from gwproto import HardwareLayout
from gwproto import create_message_model

from gwproto import MQTTCodec
from gwproto.messages import (
    Ack,
    Ping,
    ProblemEvent,
    ShutdownEvent,
    MQTTConnectEvent,
    MQTTConnectFailedEvent,
    MQTTDisconnectEvent,
    MQTTFullySubscribedEvent,
    ResponseTimeoutEvent,
    PeerActiveEvent,
)


from gwproactor import LinkSettings
from gwproactor.codecs import CodecFactory

from gwsproto.data_classes.house_0_layout import House0Layout
from gwsproto.data_classes.house_0_names import H0N

from actors.scada_interface import ScadaInterface



ScadaMessageDecoder = create_message_model(
    "ScadaMessageDecoder",
    module_names=[
        "gwsproto.named_types",
        "gwproactor.message",
    ],
    explicit_types=[
        Ack,
        Ping,
        ProblemEvent,
        ShutdownEvent,
        MQTTConnectEvent,
        MQTTConnectFailedEvent,
        MQTTDisconnectEvent,
        MQTTFullySubscribedEvent,
        ResponseTimeoutEvent,
        PeerActiveEvent,
    ],
)


class GridworksMQTTCodec(MQTTCodec):
    exp_src: str
    exp_dst: str = H0N.primary_scada

    def __init__(self, hardware_layout: House0Layout):
        self.exp_src = hardware_layout.atn_g_node_alias
        super().__init__(ScadaMessageDecoder)

    def validate_source_and_destination(self, src: str, dst: str) -> None:
        if src != self.exp_src or dst != self.exp_dst:
            raise ValueError(
                "ERROR validating src and/or dst\n"
                f"  exp: {self.exp_src} -> {self.exp_dst}\n"
                f"  got: {src} -> {dst}"
            )


class LocalMQTTCodec(MQTTCodec):
    exp_srcs: set[str]
    exp_dst: str

    def __init__(self, *, primary_scada: bool, remote_node_names: set[str]):
        self.primary_scada = primary_scada
        self.exp_srcs = remote_node_names
        if self.primary_scada:
            self.exp_srcs.add(H0N.secondary_scada)
            self.exp_dst = H0N.primary_scada
        else:
            self.exp_srcs.add(H0N.primary_scada)
            self.exp_dst = H0N.secondary_scada

        super().__init__(ScadaMessageDecoder)

    def validate_source_and_destination(self, src: str, dst: str) -> None:
        ## Black Magic 🪄
        ##   The message from scada2 contain the *spaceheat name* as
        ##   src, *not* the gnode name, in particular because they might come
        ##   from individual nodes that don't have a gnode.
        ##   Since spaceheat names now contain '-', the encoding/decoding by
        ##   MQTTCodec (done for Rabbit) is not what we we want: "-" ends up as
        ##   "." So we have undo that in this particular case.
        src = src.replace(".", "-")
        ## End Black Magic 🪄

        if dst != self.exp_dst or src not in self.exp_srcs:
            raise ValueError(
                "ERROR validating src and/or dst\n"
                f"  exp: one of {self.exp_srcs} -> {self.exp_dst}\n"
                f"  got: {src} -> {dst}"
            )


class AdminCodec(MQTTCodec):
    scada_gnode: str

    def __init__(self, scada_gnode: str):
        self.scada_gnode = scada_gnode

        super().__init__(ScadaMessageDecoder)

    def validate_source_and_destination(self, src: str, dst: str) -> None:
        if dst != self.scada_gnode or src != H0N.admin:
            raise ValueError(
                "ERROR validating src and/or dst\n"
                f"  exp: one of {H0N.admin} -> {self.scada_gnode}\n"
                f"  got: {src} -> {dst}"
            )

class ScadaCodecFactory(CodecFactory):
    ATN_MQTT: str = ScadaInterface.ATN_MQTT
    LOCAL_MQTT: str = ScadaInterface.LOCAL_MQTT
    ADMIN_MQTT: str = ScadaInterface.ADMIN_MQTT


    def get_codec(
        self,
        link_name: str,
        link: LinkSettings,
        proactor_name: ProactorName,
        layout: HardwareLayout,
    ) -> MQTTCodec:
        if not isinstance(layout, House0Layout):
            raise ValueError(
                "ERROR. ScadaCodecFactory requires hardware layout "
                "to be an instance of House0Layout but received layout type "
                f"<{type(layout)}>"
            )
        if link_name == self.ATN_MQTT:
            return GridworksMQTTCodec(layout)
        elif link_name == self.LOCAL_MQTT:
            scada_node = layout.node(H0N.primary_scada)
            remote_actor_node_names = {
                node.name
                for node in layout.nodes.values()
                if (layout.parent_node(node) != scada_node
                    and node != scada_node
                    and node.has_actor
                )
            } | {layout.scada2_gnode_name().replace(".", "-")}
            return LocalMQTTCodec(
                primary_scada=True,
                remote_node_names=remote_actor_node_names
            )
        elif link_name == self.ADMIN_MQTT:
            return AdminCodec(proactor_name.publication_name)
        return super().get_codec(
            link_name=link_name,
            link=link,
            proactor_name=proactor_name,
            layout=layout,
        )


class Scada2CodecFactory(CodecFactory):
    LOCAL_MQTT: str = "local_mqtt"

    def get_codec(
            self,
            link_name: str,
            link: LinkSettings,
            proactor_name: ProactorName,
            layout: HardwareLayout,
    ) -> MQTTCodec:
        if not isinstance(layout, House0Layout):
            raise ValueError(
                "ERROR. ScadaCodecFactory requires hardware layout "
                "to be an instance of House0Layout but received layout type "
                f"<{type(layout)}>"
            )
        if link_name == self.LOCAL_MQTT:
            return LocalMQTTCodec(
                primary_scada=False,
                remote_node_names={layout.scada_g_node_alias.replace(".", "-")}
            )
        return super().get_codec(
            link_name=link_name,
            link=link,
            proactor_name=proactor_name,
            layout=layout,
        )