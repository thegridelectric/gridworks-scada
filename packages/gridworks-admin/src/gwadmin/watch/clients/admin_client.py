import asyncio
import logging
import threading
from dataclasses import dataclass
from logging import Logger
from typing import Any
from typing import Optional
from typing import Sequence
from typing import Type

from gwproto import Message
from gwproto import Message as GWMessage
from gwproto import MQTTTopic
from gwsproto.data_classes.house_0_names import H0N
from gwproto.named_types import SendSnap
from paho.mqtt.client import MQTTMessageInfo
from pydantic import BaseModel
from result import Result

from gwadmin.settings import AdminClientSettings
from gwadmin.watch.clients.constrained_mqtt_client import ConstrainedMQTTClient
from gwadmin.watch.clients.constrained_mqtt_client import MessageReceivedCallback
from gwadmin.watch.clients.constrained_mqtt_client import MQTTClientCallbacks
from gwadmin.watch.clients.constrained_mqtt_client import StateChangeCallback
from gwsproto.named_types import LayoutLite, SendLayout, SnapshotSpaceheat

module_logger = logging.getLogger(__name__)

def type_name(model_type: Type[BaseModel]) -> str:
    if (field := model_type.model_fields.get("TypeName")) is not None:
        return str(field.default)
    return ""

@dataclass
class AdminClientCallbacks:
    """Hooks for user of AdminClient. Must be threadsafe."""

    mqtt_state_change_callback: Optional[StateChangeCallback] = None
    """Hook for user. Called when mqtt client 'state' variable changes.
    Generally, but not exclusively, called from Paho thread. Must be threadsafe.
    """

    mqtt_message_received_callback: Optional[MessageReceivedCallback] = None
    """Hook for user. Called when any mqtt message is received. Called from Paho
    thread. Must be threadsafe."""

class AdminSubClient:

    def set_admin_client(self, client: "AdminClient") -> None:
        ...

    def process_layout_lite(self, layout: LayoutLite) -> None:
        ...

    def process_snapshot(self, snapshot: SnapshotSpaceheat) -> None:
        ...


    def process_mqtt_state_changed(self, old_state: str, new_state: str) -> None:
        ...

    def process_mqtt_message(self, topic: str, payload: bytes) -> None:
        ...


class AdminClient:
    _lock: threading.RLock
    _settings: AdminClientSettings
    _paho_wrapper: ConstrainedMQTTClient
    _subclients: list[AdminSubClient]
    _callbacks: AdminClientCallbacks
    _logger: Logger | logging.LoggerAdapter[Logger] = module_logger
    _layout: Optional[LayoutLite] = None
    _snap: Optional[SnapshotSpaceheat] = None
    _init_task: Optional[asyncio.Task] = None

    def __init__(
            self,
            settings: AdminClientSettings,
            callbacks: Optional[AdminClientCallbacks] = None,
            subclients: Optional[Sequence[AdminSubClient]] = None,
            *,
            logger: Logger = module_logger,
            paho_logger: Optional[Logger] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._settings = settings.model_copy()
        self._callbacks = callbacks or AdminClientCallbacks()
        if subclients is None:
            self._subclients = []
        else:
            self._subclients = list(subclients)
            for subclient in self._subclients:
                subclient.set_admin_client(self)
        self._paho_wrapper = ConstrainedMQTTClient(
            settings=self._settings.link,
            subscriptions=[
                MQTTTopic.encode(
                    envelope_type=GWMessage.type_name(),
                    src=self._settings.target_gnode,
                    dst=H0N.admin,
                    message_type="#",
                )
            ],
            callbacks=MQTTClientCallbacks(
                state_change_callback=self._mqtt_state_changed,
                message_received_callback=self._mqtt_message_received,
            ),
            logger=logger,
            paho_logger=paho_logger,
        )
        self._logger = logger

    def set_callbacks(self, callbacks: AdminClientCallbacks) -> None:
        if self.started():
            raise ValueError(
                "ERROR. AdminClient callbacks must be set before starting "
                "the client."
            )
        self._callbacks = callbacks


    def subclients(self):
        with self._lock:
            return list(self._subclients)

    def add_subclient(self, subclient: AdminSubClient) -> None:
        subclient.set_admin_client(self)
        with self._lock:
            self._subclients.append(subclient)
        if self._layout is not None:
            subclient.process_layout_lite(self._layout)
        if self._snap is not None:
            subclient.process_snapshot(self._snap)

    async def _ensure_init(self) -> None:
        while (
            self._paho_wrapper.started()
            and self._layout is None
            and self._snap is None
        ):
            await asyncio.sleep(60)
            if self._layout is None:
                self._request_layout_lite()
            elif self._snap is None:  # noqa
                self._request_snapshot()  # noqa

    def start(self):
        self._paho_wrapper.start()
        self._init_task = asyncio.create_task(self._ensure_init())

    def stop(self):
        if self._init_task is not None and not self._init_task.cancelled():
            self._init_task.cancel()
        self._init_task = None
        self._paho_wrapper.stop()

    def started(self) -> bool:
        return self._paho_wrapper.started()

    def publish(self, payload: Any) -> Result[MQTTMessageInfo, Exception | None]:
        message = Message[Any](
            Dst=self._settings.target_gnode,
            Src=H0N.admin,
            Payload=payload
        )
        return self._paho_wrapper.publish(
            message.mqtt_topic(),
            message.model_dump_json(indent=2).encode()
        )

    def _request_layout_lite(self) -> None:
        self.publish(
            SendLayout(
                FromGNodeAlias=H0N.admin,
                FromName=H0N.admin,
                ToName=H0N.primary_scada,
            )
        )

    def _request_snapshot(self) -> None:
        self.publish(SendSnap(FromGNodeAlias=H0N.admin))

    def _mqtt_state_changed(self, old_state: str, new_state: str) -> None:
        try:
            if new_state == ConstrainedMQTTClient.States.active:
                self._request_layout_lite()
            for subclient in self._subclients:
                subclient.process_mqtt_state_changed(old_state, new_state)
            if self._callbacks.mqtt_state_change_callback:
                self._callbacks.mqtt_state_change_callback(old_state, new_state)
        except Exception as e:
            self._logger.exception(
                "ERROR in AdminClient._mqtt_state_changed("
                f"{old_state}, {new_state}): ",
                f"<{type(e)}>: <{e}>",
            )

    def _process_layout_lite(self, payload: bytes) -> None:
        message = Message[LayoutLite].model_validate_json(payload)
        self._layout = message.Payload
        self._request_snapshot()
        for subclient in self.subclients():
            subclient.process_layout_lite(self._layout)

    def _process_snapshot(self, payload: bytes) -> None:
        # self._logger.debug("++AdminClient._process_snapshot")
        path_dbg = 0
        path_count = 0
        message = Message[SnapshotSpaceheat].model_validate_json(payload)
        self._snap = message.Payload
        for subclient in self.subclients():
            path_dbg |= 0x00000001
            path_count += 1
            subclient.process_snapshot(self._snap)
        # self._logger.debug(
        #     "++AdminClient._process_snapshot  path:0x%08X  count:%d",
        #     path_dbg, path_count,
        # )

    def _mqtt_message_received(self, topic: str, payload: bytes) -> None:
        path_dbg = 0
        # self._logger.debug("++AdminClient._mqtt_message_received  <%s>", topic)
        try:
            decoded_topic = MQTTTopic.decode(topic)
            if decoded_topic.message_type == type_name(LayoutLite):
                path_dbg |= 0x00000001
                self._process_layout_lite(payload)
            elif decoded_topic.message_type == type_name(SnapshotSpaceheat):
                path_dbg |= 0x00000002
                self._process_snapshot(payload)
            else:
                path_dbg |= 0x00000004
                for subclient in self.subclients():
                    path_dbg |= 0x00000008
                    subclient.process_mqtt_message(topic, payload)
            if self._callbacks.mqtt_message_received_callback is not None:
                path_dbg |= 0x00000010
                self._callbacks.mqtt_message_received_callback(topic, payload)
        except Exception as e:
            path_dbg |= 0x00000020
            self._logger.exception(
                (
                    "ERROR in AdminClient mqtt message received callback: ",
                    f"<{type(e)}>: <{e}> for topic: <{topic}>"
                ),
            )
        # self._logger.debug("--AdminClient._mqtt_message_received  path:0x%08X", path_dbg)

