"""Parentless (Scada2) implementation"""
import typing
from typing import Any, Optional

from gwproactor import CodecFactory
from gwproactor import LinkSettings
from gwproactor import PrimeActor
from gwproactor import ProactorLogger
from gwproactor import ProactorName
from gwproactor import AppInterface
from gwproto import HardwareLayout
from gwproto import MQTTCodec
from gwproto.message import Header
from gwproto.message import Message
from gwproto.named_types import PowerWatts, Report, SyncedReadings

from data_classes.house_0_names import H0N
from data_classes.house_0_layout import House0Layout
from gwproto.data_classes.sh_node import ShNode

from actors.config import ScadaSettings
from gwproactor import QOS
from gwproactor.message import MQTTReceiptPayload
from actors.codec_factories import Scada2CodecFactory
from named_types import Glitch, SnapshotSpaceheat




class Scada2Data:
    latest_snap: Optional[SnapshotSpaceheat]
    latest_report: Optional[Report]
    def __init__(self) -> None:
        self.latest_snap = None
        self.latest_report = None

class Parentless(PrimeActor):
    ASYNC_POWER_REPORT_THRESHOLD = 0.05
    DEFAULT_ACTORS_MODULE = "actors"
    LOCAL_MQTT: str = Scada2CodecFactory.LOCAL_MQTT
    _data: Scada2Data
    _publication_name: str

    def __init__(self, name: str, services: AppInterface) -> None:
        if not isinstance(services.hardware_layout, House0Layout):
            raise Exception("Make sure to pass House0Layout object as hardware_layout!")
        super().__init__(name, services)
        self._data = Scada2Data()

    @property
    def hardware_layout(self) -> House0Layout:
        return typing.cast(House0Layout, self.services.hardware_layout)

    @property
    def layout(self) -> House0Layout:
        return self.hardware_layout

    @classmethod
    def get_codec_factory(cls) -> Scada2CodecFactory:
        return Scada2CodecFactory()

    def init(self) -> None:
        """Called after constructor so derived functions can be used in setup."""

    @property
    def name(self):
        return self.services.name

    @property
    def node(self) -> ShNode:
        return self._node

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
            Parentless.LOCAL_MQTT,
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
                        Dst=H0N.primary_scada,
                        MessageType=message.Payload.TypeName,
                        ),
                    Payload=message.Payload
                )
                self.services.publish_message(
                    Parentless.LOCAL_MQTT,
                    new_msg,
                    QOS.AtMostOnce,
                    use_link_topic=True,
                )
            case PowerWatts():
                new_msg = Message(
                    Header=Header(
                        Src=message.Header.Src, 
                        Dst=H0N.primary_scada,
                        MessageType=message.Payload.TypeName,
                        ),
                    Payload=message.Payload
                )
                self.services.publish_message(
                    Parentless.LOCAL_MQTT,
                    new_msg,
                    QOS.AtMostOnce,
                    use_link_topic=True,
                )
            case SyncedReadings():
                path_dbg |= 0x00000004
                new_msg = Message(
                    Header=Header(
                        Src=message.Header.Src, 
                        Dst=H0N.primary_scada,
                        MessageType=message.Payload.TypeName,
                        ),
                    Payload=message.Payload
                )
                self.services.publish_message(
                    Parentless.LOCAL_MQTT,
                    new_msg,
                    QOS.AtMostOnce,
                    use_link_topic=True,
                )
            case _:
                raise ValueError(
                    f"There is no handler for message payload type [{type(message.Payload)}]"
                )
        self.logger.path("--Parentless.process_internal_message  path:0x%08X", path_dbg)

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
    
