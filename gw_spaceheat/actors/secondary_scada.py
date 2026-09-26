"""Parentless (Scada2) implementation"""
import typing
from typing import Any, NamedTuple, Optional

from gwproactor import PrimeActor
from gwproactor import ProactorLogger
from gwproto.message import Header
from gwproto.message import Message

from actors import ContractHandler
from gwsproto.data_classes.hydronic_layout import HydronicLayout

from gwsproto.data_classes.sh_node import ShNode

from actors.config import ScadaSettings
from gwproactor import QOS
from gwproactor.links.link_state import Transition
from gwproactor.message import MQTTReceiptPayload
from gwsproto.named_types import PowerWatts, Report, SyncedReadings
from actors.codec_factories import Scada2CodecFactory
from gwsproto.named_types import Glitch, SnapshotSpaceheat
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.property_format import SpaceheatName, UTCMilliseconds
from actors.scada_interface import ScadaInterface

from scada_app_interface import ScadaAppInterface


class ForwardedReading(NamedTuple):
    """The latest reading scada2 has forwarded for one channel: the node it
    came from, the value, and the time it was read."""

    src: SpaceheatName
    value: int
    read_time_ms: UTCMilliseconds


class Scada2Data:
    latest_snap: Optional[SnapshotSpaceheat]
    latest_report: Optional[Report]
    latest_forwarded: dict[SpaceheatName, ForwardedReading]
    def __init__(self) -> None:
        self.latest_snap = None
        self.latest_report = None
        self.latest_forwarded = {}

class SecondaryScada(PrimeActor, ScadaInterface):
    ASYNC_POWER_REPORT_THRESHOLD = 0.05
    DEFAULT_ACTORS_MODULE = "actors"
    LOCAL_MQTT: str = Scada2CodecFactory.LOCAL_MQTT
    _data: Scada2Data
    _publication_name: str

    def __init__(self, name: str, services: ScadaAppInterface) -> None:
        if not isinstance(services.hardware_layout, HydronicLayout):
            raise Exception("Make sure to pass HydronicLayout object as hardware_layout!")
        super().__init__(name, services)
        self._actor_node = services.hardware_layout.node(name)
        self._data = Scada2Data()

    @property
    def hardware_layout(self) -> HydronicLayout:
        return typing.cast(HydronicLayout, self.services.hardware_layout)

    @property
    def layout(self) -> HydronicLayout:
        return self.hardware_layout

    @property
    def contract_handler(self) -> ContractHandler:
        raise ValueError("ERROR. Parentless does not have a contract handler")

    @classmethod
    def get_codec_factory(cls) -> Scada2CodecFactory:
        return Scada2CodecFactory()

    def init(self) -> None:
        """Called after constructor so derived functions can be used in setup."""

    @property
    def node(self) -> ShNode:
        return self.layout.node(self.name)

    @property
    def publication_name(self) -> str:
        return self.services.publication_name

    @property
    def subscription_name(self) -> str:
        return self.services.subscription_name

    @property
    def settings(self) -> ScadaSettings:
        return typing.cast(ScadaSettings, self.services.settings)

    @property
    def data(self) -> Scada2Data:
        return self._data  
 
    @property
    def logger(self) -> ProactorLogger:
        return self.services.logger

    def _publish_to_local(self, from_node: ShNode, payload, qos: QOS = QOS.AtMostOnce):
        return self.services.publish_message(
            SecondaryScada.LOCAL_MQTT,
            Message(Src=from_node.Name, Payload=payload),
            qos=qos,
            use_link_topic=True
        )

    def process_internal_message(self, message: Message[Any]) -> None:
        self.logger.path("++Parentless.process_internal_message %s/%s", message.Header.Src, message.Header.MessageType)
        path_dbg = 0
        match message.Payload:
            case Glitch():
                new_msg = Message(
                    Header=Header(
                        Src=message.Header.Src, 
                        Dst=CoreNodeNames.primary_scada,
                        MessageType=message.Payload.TypeName,
                        ),
                    Payload=message.Payload
                )
                self.services.publish_message(
                    SecondaryScada.LOCAL_MQTT,
                    new_msg,
                    QOS.AtMostOnce,
                    use_link_topic=True,
                )
            case PowerWatts():
                new_msg = Message(
                    Header=Header(
                        Src=message.Header.Src, 
                        Dst=CoreNodeNames.primary_scada,
                        MessageType=message.Payload.TypeName,
                        ),
                    Payload=message.Payload
                )
                self.services.publish_message(
                    SecondaryScada.LOCAL_MQTT,
                    new_msg,
                    QOS.AtMostOnce,
                    use_link_topic=True,
                )
            case SyncedReadings():
                path_dbg |= 0x00000004
                self.forward_synced_readings(message.Header.Src, message.Payload)
            case _:
                raise ValueError(
                    f"There is no handler for message payload type [{type(message.Payload)}]"
                )
        self.logger.path("--Parentless.process_internal_message  path:0x%08X", path_dbg)

    def forward_synced_readings(self, src: str, readings: SyncedReadings) -> None:
        """Send the readings to the scada and keep each channel's latest, so
        it can be sent again when the link to the scada goes active."""
        for channel_name, value in zip(readings.ChannelNameList, readings.ValueList):
            self._data.latest_forwarded[channel_name] = ForwardedReading(
                src=src, value=value, read_time_ms=readings.ScadaReadTimeUnixMs
            )
        self.services.publish_message(
            SecondaryScada.LOCAL_MQTT,
            Message(
                Header=Header(
                    Src=src,
                    Dst=CoreNodeNames.primary_scada,
                    MessageType=readings.TypeName,
                ),
                Payload=readings,
            ),
            QOS.AtMostOnce,
            use_link_topic=True,
        )

    def recv_activated(self, transition: Transition) -> None:
        """Re-send the latest reading of every channel forwarded so far, with
        the original read times, each time the link to the scada goes active.
        The readings travel at QoS 0 with no ack, so a report the scada was
        not ready for is gone; the re-send is what covers it."""
        if transition.link_name != self.services.upstream_client:
            return
        batches: dict[tuple[SpaceheatName, UTCMilliseconds], list[tuple[SpaceheatName, int]]] = {}
        for channel_name, reading in self._data.latest_forwarded.items():
            batches.setdefault((reading.src, reading.read_time_ms), []).append(
                (channel_name, reading.value)
            )
        for (src, read_time_ms), channel_values in batches.items():
            self.forward_synced_readings(
                src,
                SyncedReadings(
                    ChannelNameList=[name for name, _ in channel_values],
                    ValueList=[value for _, value in channel_values],
                    ScadaReadTimeUnixMs=read_time_ms,
                ),
            )

    def process_mqtt_message(
        self, mqtt_client_message: Message[MQTTReceiptPayload], decoded: Message[Any]
    ) -> None:
        self.logger.path("++Parentless.process_mqtt_message %s", mqtt_client_message.Payload.message.topic)
        path_dbg = 0
        match decoded.Payload:
            case Report():
                path_dbg |= 0x00000001
                self.process_report(decoded.Payload)
            case SnapshotSpaceheat():
                path_dbg |= 0x00000002
                self.process_snapshot(decoded.Payload)
            case _:
                # Intentionally ignored for forward compatibility
                path_dbg |= 0x00000004
        self.logger.path("--Parentless.process_mqtt_message  path:0x%08X", path_dbg)

    def process_snapshot(self, payload: SnapshotSpaceheat)-> None:
        self._data.latest_snap = payload

    def process_report(self, payload: Report)-> None:
        self._data.latest_report = payload
    
