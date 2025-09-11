import contextlib
import logging
import ssl
import threading
import uuid
from dataclasses import dataclass
from enum import auto
from enum import StrEnum
from logging import Logger
from logging import LoggerAdapter
from typing import Any
from typing import Callable
from typing import Optional
from typing import Sequence

from gwproactor import responsive_sleep
from gwproactor.config import MQTTClient as MQTTClientSettings
from paho.mqtt.client import Client as MQTTClient
from paho.mqtt.client import MQTT_ERR_SUCCESS
from paho.mqtt.client import MQTTMessage
from paho.mqtt.client import MQTTMessageInfo
from paho.mqtt.enums import CallbackAPIVersion
from result import Err
from result import Ok
from result import Result

module_logger = logging.getLogger(__name__)

StateChangeCallback = Callable[[str, str], None]
MessageReceivedCallback = Callable[[str, bytes], None]

@dataclass
class MQTTClientCallbacks:
    """Hooks for user of ConstrainedMQTTClient. Must be threadsafe."""

    state_change_callback: Optional[StateChangeCallback] = None
    """Hook for user. Called when ConstrainedMQTTClient 'state'
    variable changes. Generally, but not exclusively, called from Paho thread.
    Must be threadsafe. 
    """

    message_received_callback: Optional[MessageReceivedCallback] = None
    """Hook for user. Called when a message is received. Called from Paho thread.
     Must be threadsafe."""

class ConstrainedMQTTClient:
    """A simple mqtt client providing:

        1. MQTT loop in a separate thread, with auto-reconnect with backoff on
           uhandled error.
        2. Auto-resubscribe.
        3. A Callback hook for receiving messages, which takes a topic and payload.
        4. A Callback hook for communication state changes, which takes a string
            for the previous state and a string for the current state.
        5. A thread-safe publish method.

        The state transitions are approximately:
            Constructed -> stopped
            stopped -> started (via start())
            started -> connecting (automatically)
            connecting -> subscribing (automatically)
            subscribing -> active (automatically)

            Subscribing/active -> connecting (via broker connection issue)

            Any state except stopped -> backing_off (via unhandled error)
            backing_off -> started (automatically after backoff delay)

            Any state -> stopped (via stop())

        Restrictions:
            Subscriptions can only be provided via the constructor.
            QOS for publish and subscribe is restricted to "At Most Once".
        """

    class States(StrEnum):
        stopped = auto()  # noqa
        started = auto()  # noqa
        connecting = auto()  # noqa
        subscribing = auto()  # noqa
        active = auto()  # noqa
        backing_off = auto()  # noqa

    _state: States = States.stopped
    """Enum/string representation of connectivity providing feedback to user"""

    _lock: threading.RLock
    """Used to allow errors in publish to cause a clean restart"""

    _client: Optional[MQTTClient]
    """Tha Paho MQTT client"""

    _stop_requested: bool = False
    """Tells thread whether to continue after Paho loop exits"""

    _thread: Optional[threading.Thread] = None
    """Thread housing the Paho loop and providing re-creation of Paho client
    on unhandled error."""

    _settings: MQTTClientSettings
    """MQTT configuration."""

    _subscriptions: set[str]
    """Topics to subscribe to following each connection to broker."""

    _pending_subscriptions: set[str]
    """Topics we currently need to resubscribe to."""

    _pending_subacks: dict[int, set[str]]
    """Subcriptions waiting for acks."""

    _callbacks: MQTTClientCallbacks
    """Hooks for user called when '_state' variable changes and when a message 
    is received."""

    _logger: Logger | LoggerAdapter[Logger] = module_logger
    """Configurable logger used by this class. """

    _paho_logger: Logger | LoggerAdapter[Logger] = None
    """Configurable logger used by Paho"""

    def __init__(
        self,
        settings: MQTTClientSettings,
        subscriptions: Sequence[str],
        callbacks: Optional[MQTTClientCallbacks] = None,
        *,
        logger: Optional[Logger] = None,
        paho_logger: Optional[Logger] = None,
    ):
        self._lock = threading.RLock()
        self._settings = settings.model_copy()
        self._subscriptions = set(subscriptions)
        self._callbacks = callbacks or MQTTClientCallbacks()
        if logger is not None:
            self._logger = logger
        if paho_logger is not None:
            self._paho_logger = paho_logger
        self._client = None
        self._pending_subscriptions = set(self._subscriptions)
        self._pending_subacks = {}

    def _subscribe_all(self) -> tuple[int, Optional[int]]:
        subscribe_result: tuple[int, Optional[int]]
        if self._subscriptions:
            subscribe_result = self._client.subscribe(
                [(topic, 0) for topic in self._subscriptions]
            )
            if subscribe_result[0] == MQTT_ERR_SUCCESS:
                self._pending_subacks[subscribe_result[1]] = set(self._subscriptions)
        else:
            subscribe_result = MQTT_ERR_SUCCESS, None
        return subscribe_result

    def num_subscriptions(self) -> int:
        return len(self._subscriptions)

    def num_pending_subscriptions(self) -> int:
        return len(self._pending_subscriptions)

    def set_logger(self, logger: Logger, paho_logger: Optional[Logger] = None):
        self._logger = logger
        self._paho_logger = paho_logger
        with self._lock:
            if self._client is not None:
                self._client.enable_logger(self._paho_logger)

    def _change_state(self, new_state: States) -> bool:
        with self._lock:
            old_state = self._state
            self._state = new_state
        if (
                old_state != new_state
                # Do not issue callback *during* start() call.
                and not (
                    old_state == self.States.stopped
                    and new_state == self.States.started
                )
                and self._callbacks.state_change_callback is not None
        ):
            self._callbacks.state_change_callback(old_state, new_state)
        if old_state != new_state:
            self._logger.debug("MQTTClient: %s -> %s", old_state, new_state)
        return old_state != new_state

    def start(self):
        with self._lock:
            if self._thread is None:
                self._change_state(self.States.started)
                self._stop_requested = False
                self._thread = threading.Thread(
                    target=self._client_thread,
                    name="admin-MQTT-client-thread"
                )
                self._thread.start()

    def stop(self):
        with self._lock:
            if self.started():
                self._stop_requested = True
            paho_client = self._client
        if paho_client is not None:
            with contextlib.suppress(Exception):
                paho_client.disconnect()
            paho_client._thread_terminate = True

    def started(self) -> bool:
        with self._lock:
            return self._thread is not None

    def publish(self, topic: str, payload: bytes) -> Result[MQTTMessageInfo, Exception | None]:
        with self._lock:
            try:
                if self._client is not None:
                    result = Ok(self._client.publish(topic, payload, 0))
                else:
                    result = Err(None)
            except Exception as e:  # noqa
                result = Err(e)
                with contextlib.suppress(Exception):
                    self._client.disconnect()
                self._client._thread_terminate = True
        return result

    def _on_connect(self, _: Any, _userdata: Any, _flags: dict, _rc: int, _properties: Any) -> None:
        self._change_state(self.States.subscribing)
        self._subscribe_all()

    def _on_subscribe(
        self, _: Any, _userdata: Any, mid: int, _granted_qos: list[int], _properties: Any
    ) -> None:
        topics = self._pending_subacks.pop(mid, [])
        if topics:
            for topic in topics:
                self._pending_subscriptions.remove(topic)
        if not self._pending_subscriptions:
            with self._lock:
                if self._state == self.States.subscribing:
                    self._change_state(self.States.active)

    def _on_connect_fail(self, _: Any, _userdata: Any) -> None:
        self._change_state(self.States.connecting)

    def _on_disconnect(self, _: Any, _userdata: Any, _rc: int, _properties: Any, stuff: Any) -> None:
        self._pending_subscriptions = set(self._subscriptions)

    def _on_message(self, _: Any, _userdata: Any, message: MQTTMessage) -> None:
        if self._callbacks.message_received_callback is not None:
            self._callbacks.message_received_callback(
                message.topic,
                message.payload  # noqa
            )

    def _make_client(self) -> Result[bool, Exception]:
        with self._lock:
            try:
                self._client = MQTTClient(
                    callback_api_version=CallbackAPIVersion.VERSION2,
                    client_id="-".join(str(uuid.uuid4()).split("-")[:-1])
                )
                if self._paho_logger is not None:
                    self._client.enable_logger(self._paho_logger)
                self._client.username_pw_set(
                    username=self._settings.username,
                    password=self._settings.password.get_secret_value(),
                )
                tls_config = self._settings.tls
                if tls_config.use_tls:
                    self._client.tls_set(
                        ca_certs=tls_config.paths.ca_cert_path,
                        certfile=tls_config.paths.cert_path,
                        keyfile=tls_config.paths.private_key_path,
                        cert_reqs=tls_config.cert_reqs,
                        tls_version=ssl.PROTOCOL_TLS_CLIENT,
                        ciphers=tls_config.ciphers,
                        keyfile_password=tls_config.keyfile_password.get_secret_value(),
                    )
                self._client.on_message = self._on_message
                self._client.on_connect = self._on_connect
                self._client.on_connect_fail = self._on_connect_fail
                self._client.on_disconnect = self._on_disconnect
                self._client.on_subscribe = self._on_subscribe
                result = Ok()
            except Exception as e:
                self._logger.exception(f"ERROR creating MQTT client: <{type(e)}>  <{e}>")
                result = Err(e)
                self._client = None
        return result

    def _client_thread(self) -> None:
        max_back_off = 1024
        backoff = 1
        try:
            while not self._stop_requested:
                try:
                    self._change_state(self.States.started)
                    match self._make_client():
                        case Ok():
                            self._change_state(self.States.connecting)
                            self._client.connect(
                                self._settings.host,
                                port=self._settings.effective_port(),
                            )
                            self._client.loop_forever(retry_first_connection=True)
                        case Err() as err:
                            self._logger.exception(
                                "Exception creating mqtt client: "
                                f" <{type(err.err())}> "
                                f" <{err.err()}> "
                                "Restarting loop"
                            )
                except: # noqa
                    self._logger.exception(
                        "Exception in main mqtt loop. Restarting loop"
                    )
                finally:
                    with self._lock:
                        self._change_state(self.States.backing_off)
                        if self._client is not None:
                            with contextlib.suppress(Exception):
                                self._client.disconnect()
                            self._client = None
                if not self._stop_requested:
                    if backoff >= max_back_off:
                        backoff = 1
                    else:
                        backoff = min(backoff * 2, max_back_off)
                    responsive_sleep(
                        self,
                        backoff,
                        running_field_name="_stop_requested",
                        running_field=False,
                    )
        finally:
            with self._lock:
                self._change_state(self.States.stopped)
                self._thread = None
