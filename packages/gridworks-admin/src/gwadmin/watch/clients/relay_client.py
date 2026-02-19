import copy
import datetime
import logging
import threading
import uuid
from dataclasses import dataclass
from enum import auto
from enum import StrEnum
from logging import Logger
from typing import Callable
from typing import Optional
from typing import Self
from typing import Sequence

from gwproto import Message as GWMessage
from gwproto import MQTTTopic
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import ActorClass, ChangeRelayPin


from gwsproto.named_types import SingleReading
from pydantic import BaseModel
from pydantic import model_validator

from gwadmin.watch.clients.admin_client import type_name
from gwadmin.watch.clients.admin_client import AdminClient
from gwadmin.watch.clients.admin_client import AdminSubClient
from gwadmin.watch.clients.constrained_mqtt_client import MessageReceivedCallback
from gwadmin.watch.clients.constrained_mqtt_client import StateChangeCallback
from gwsproto.named_types import (AdminDispatch,  AdminKeepAlive, AdminReleaseControl,
                         FsmEvent, LayoutLite, SnapshotSpaceheat)
from gwsproto.enums import TurnHpOnOff

module_logger = logging.getLogger(__name__)

class RelayConfig(BaseModel):
    about_node_name: str = ""
    channel_name: str = ""
    event_type: str = ""
    energizing_event: str = ""
    de_energizing_event: str = ""
    energized_state: str = ""
    deenergized_state: str = ""

class RelayEnergized(StrEnum):
    deenergized = auto()
    energized = auto()

class RelayState(BaseModel):
    value: RelayEnergized
    time: datetime.datetime

class RelayInfo(BaseModel):
    config: RelayConfig
    observed: Optional[RelayState] = None

class ObservedRelayStateChange(BaseModel):
    old_state: Optional[RelayState] = None
    new_state: Optional[RelayState] = None

    @model_validator(mode="after")
    def _model_validator(self) -> Self:
        if self.old_state == self.new_state:
            raise ValueError(
                f"ERROR ObservedRelayStateChange has no change: {self.old_state}"
            )
        return self

RelayStateChangeCallback = Callable[[dict[str, ObservedRelayStateChange]], None]
LayoutCallback = Callable[[LayoutLite], None]
SnapshotCallback = Callable[[SnapshotSpaceheat], None]

class RelayConfigChange(BaseModel):
    old_config: Optional[RelayConfig] = None
    new_config: Optional[RelayConfig] = None

    @model_validator(mode="after")
    def _model_validator(self) -> Self:
        if self.old_config == self.new_config:
            raise ValueError(
                f"ERROR RelayConfigChange has no change: {self.old_config}"
            )
        return self

RelayConfigChangeCallback = Callable[[dict[str, RelayConfigChange]], None]

@dataclass
class RelayClientCallbacks:
    """Hooks for user of RelayWatchClient. Must be threadsafe."""

    mqtt_state_change_callback: Optional[StateChangeCallback] = None
    """Hook for user. Called when mqtt client 'state'
    variable changes. Generally, but not exclusively, called from Paho thread.
    Must be threadsafe."""

    mqtt_message_received_callback: Optional[MessageReceivedCallback] = None
    """Hook for user. Called when an mqtt message is received if that message is 
     not relay-related or 'pass_all_messages' is True. Called from Paho thread.
     Must be threadsafe."""

    relay_state_change_callback: Optional[RelayStateChangeCallback] = None
    """Hook for user. Called when a relay state change is observed. 
    Called from Paho thread. Must be threadsafe."""

    relay_config_change_callback: Optional[RelayConfigChangeCallback] = None
    """Hook for user. Called when a relay config change is observed. 
    Called from Paho thread. Must be threadsafe."""

    layout_callback: Optional[LayoutCallback] = None
    """Hook for user. Called when a layout received. Called from Paho thread. 
    Must be threadsafe."""

    snapshot_callback: Optional[SnapshotCallback] = None
    """Hook for user. Called when a snapshot received. Called from Paho thread. 
    Must be threadsafe."""

class RelayWatchClient(AdminSubClient):
    _lock: threading.RLock
    _relays: dict[str, RelayInfo]
    _channel2node: dict[str, str]
    _pass_all_message: bool = False
    _admin_client: AdminClient
    _callbacks: RelayClientCallbacks
    _layout: Optional[LayoutLite] = None
    _snap: Optional[SnapshotSpaceheat] = None
    _logger: Logger | logging.LoggerAdapter[Logger] = module_logger

    def __init__(
            self,
            callbacks: Optional[RelayClientCallbacks] = None,
            *,
            pass_all_messages: bool = False,
            logger: Optional[Logger | logging.LoggerAdapter[Logger]] = module_logger,
    ) -> None:
        self._lock = threading.RLock()
        self._callbacks = callbacks or RelayClientCallbacks()
        self._logger = logger
        self._relays = {}
        self._channel2node = {}
        self._pass_all_message = pass_all_messages

    def set_admin_client(self, client: AdminClient) -> None:
        self._admin_client = client

    def set_callbacks(self, callbacks: RelayClientCallbacks) -> None:
        if self._admin_client.started():
            raise ValueError(
                "ERROR. AdminClient callbacks must be set before starting "
                "the client."
            )
        self._callbacks = callbacks

    @classmethod
    def _get_relay_configs(cls, layout: LayoutLite) -> dict[str, RelayConfig]:
        relay_node_names = {node.Name for node in layout.ShNodes if node.ActorClass == ActorClass.Relay}
        relay_channels = {channel.AboutNodeName: channel for channel in layout.DataChannels if channel.AboutNodeName in relay_node_names}
        relay_actor_configs = {config.ActorName: config for config in layout.I2cRelayComponent.ConfigList}
        return {
            node_name : RelayConfig(
                about_node_name=node_name,
                channel_name=relay_channels[node_name].Name,
                event_type=relay_actor_configs[node_name].EventType,
                energizing_event=relay_actor_configs[node_name].EnergizingEvent,
                de_energizing_event=relay_actor_configs[node_name].DeEnergizingEvent,
                energized_state=relay_actor_configs[node_name].EnergizedState,
                deenergized_state=relay_actor_configs[node_name].DeEnergizedState,
            ) for node_name in relay_node_names
        }

    def _update_layout(self, new_layout: LayoutLite) -> dict[str, RelayConfigChange]:
        with self._lock:
            self._layout = new_layout.model_copy()
            new_relay_configs = self._get_relay_configs(self._layout)
            old_relay_names = set(self._relays.keys())
            new_relay_names = set(new_relay_configs.keys())
            changed_configs = {}
            for added_relay_name in (new_relay_names - old_relay_names):
                self._relays[added_relay_name] = RelayInfo(
                    config=new_relay_configs[added_relay_name],
                )
                changed_configs[added_relay_name] = RelayConfigChange(
                    old_config=None,
                    new_config=new_relay_configs[added_relay_name],
                )
            for removed_relay_name in (old_relay_names - new_relay_names):
                changed_configs[removed_relay_name] = RelayConfigChange(
                    old_config=self._relays.pop(removed_relay_name).config,
                    new_config=None,
                )
            for relay_name in new_relay_names.intersection(old_relay_names):
                new_config = new_relay_configs[relay_name]
                if new_config != self._relays[relay_name].config:
                    changed_configs[relay_name] = RelayConfigChange(
                        old_config=self._relays[relay_name].config,
                        new_config=new_config,
                    )
                    self._relays[relay_name].config = new_config
            if changed_configs:
                self._channel2node = {
                    relay.config.channel_name: relay.config.about_node_name
                    for relay in self._relays.values()
                }
        return changed_configs

    def process_layout_lite(self, layout: LayoutLite) -> None:
        config_changes = self._update_layout(layout)
        if config_changes and self._callbacks.relay_config_change_callback is not None:
            self._callbacks.relay_config_change_callback(config_changes)
        if self._callbacks.layout_callback is not None:
            self._callbacks.layout_callback(layout)
        if self._snap is not None:
           self._process_snapshot(self._snap)

    def _update_relay_states(self, new_states: dict[str, RelayState]) -> dict[str, ObservedRelayStateChange]:
        changes: dict[str, ObservedRelayStateChange] = {}
        with self._lock:
            for relay_name, new_state in new_states.items():
                relay_info = self._relays.get(relay_name)
                if relay_info is not None:
                    old_state = copy.deepcopy(relay_info.observed)
                    if old_state != new_state:
                        if old_state is None or new_state.time > old_state.time:
                            relay_info.observed = new_state
                            changes[relay_name] = ObservedRelayStateChange(
                                old_state=old_state,
                                new_state=new_state,
                            )
        return changes

    def _handle_new_relay_states(self, new_states: dict[str, RelayState]) -> None:
        state_changes = self._update_relay_states(new_states)
        if state_changes and self._callbacks.relay_state_change_callback is not None:
            self._callbacks.relay_state_change_callback(state_changes)

    def _relay_info_from_channel(self, channel_name: str) -> Optional[RelayInfo]:
        return self._relays.get(
            self._channel2node.get(channel_name, ""), None
        )

    def _extract_relay_states(self, readings: Sequence[SingleReading]) -> dict[str, RelayState]:
        states = {}
        for reading in readings:
            if relay_info := self._relay_info_from_channel(reading.ChannelName):
                states[relay_info.config.about_node_name] = RelayState(
                    value=RelayEnergized.energized if reading.Value else RelayEnergized.deenergized,
                    time=reading.ScadaReadTimeUnixMs,
                )
        return states

    def _process_single_reading(self, payload: bytes) -> None:
        if self._layout is not None:
            self._handle_new_relay_states(
                self._extract_relay_states(
                    [GWMessage[SingleReading].model_validate_json(payload).Payload]
                )
            )

    def process_snapshot(self, snapshot: SnapshotSpaceheat) -> None:
        # self._logger.debug("++RelayWatchClient.process_snapshot")
        path_dbg = 0
        self._process_snapshot(snapshot)
        if self._callbacks.snapshot_callback is not None:
            path_dbg |= 0x0000001
            self._callbacks.snapshot_callback(snapshot)
        # self._logger.debug("--RelayWatchClient.process_snapshot  path:0x%08X", path_dbg)

    def _process_snapshot(self, snapshot: SnapshotSpaceheat) -> None:
        if self._layout is not None:
            self._handle_new_relay_states(
                self._extract_relay_states(snapshot.LatestReadingList)
            )

    def process_mqtt_state_changed(self, old_state: str, new_state: str) -> None:
        if self._callbacks.mqtt_state_change_callback is not None:
            self._callbacks.mqtt_state_change_callback(old_state, new_state)

    def process_mqtt_message(self, topic: str, payload: bytes) -> None:
        decoded_topic = MQTTTopic.decode(topic)
        if decoded_topic.message_type == type_name(SingleReading):
            self._process_single_reading(payload)
        if self._callbacks.mqtt_message_received_callback is not None:
            self._callbacks.mqtt_message_received_callback(topic, payload)

    def scada_selection_reset(self) -> None:
        self._layout = None
        self._snap = None
        with self._lock:
            removed_relays = self._relays
            self._relays = {}
            self._channel2node = {}
        if removed_relays and self._callbacks.relay_config_change_callback is not None:
            self._callbacks.relay_config_change_callback(
                {
                    relay_name: RelayConfigChange(
                        old_config=relay.config,
                        new_config=None,
                    )
                    for relay_name, relay in removed_relays.items()
                 }
            )

    def set_relay(self, relay_node_name: str, new_state: RelayEnergized, timeout_seconds: Optional[int] = None):
        if new_state == RelayEnergized.energized:
            trigger = ChangeRelayPin.Energize
        else:
            trigger = ChangeRelayPin.DeEnergize
        self._send_set_command(relay_node_name, trigger, datetime.datetime.now(), timeout_seconds)

    def _send_set_command(
            self,
            relay_name: str,
            trigger: ChangeRelayPin,
            set_time: datetime.datetime,
            timeout_seconds: Optional[int] = None
    ) -> None:

        relay_config = self._relays[relay_name].config

        to_handle = f"{H0N.admin}.{relay_name}"
        event_type = relay_config.event_type
        event_name = (
                relay_config.energizing_event
                if trigger == ChangeRelayPin.Energize
                else relay_config.de_energizing_event
        )
        # TODO: if flow manifold variant is House0Sieg
        if relay_name == H0N.hp_scada_ops_relay:
            to_handle = f"{H0N.admin}.{H0N.hp_boss}"
            event_type = TurnHpOnOff.enum_name()
            if trigger == ChangeRelayPin.DeEnergize:
                event_name = TurnHpOnOff.TurnOn
            else:
                event_name = TurnHpOnOff.TurnOff

        event = FsmEvent(
            FromHandle=H0N.admin,
            ToHandle=to_handle,
            EventType=event_type,
            EventName=event_name,
            SendTimeUnixMs=int(set_time.timestamp() * 1000),
            TriggerId=str(uuid.uuid4()),
        )
        self._admin_client.publish(
            AdminDispatch(
                DispatchTrigger=event,
                TimeoutSeconds=timeout_seconds
            )
        )


    def send_keepalive(self, timeout_seconds: Optional[int] = None) -> None:
        self._admin_client.publish(
            AdminKeepAlive(AdminTimeoutSeconds=timeout_seconds)
        )

    def send_release_control(self) -> None:
        self._admin_client.publish(
            AdminReleaseControl()
        )

