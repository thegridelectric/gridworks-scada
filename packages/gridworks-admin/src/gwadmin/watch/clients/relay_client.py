import copy
import datetime
import logging
import threading
import uuid
from dataclasses import dataclass
from logging import Logger
from typing import Callable
from typing import Optional
from typing import Self
from typing import Sequence

from gwproto import Message as GWMessage
from gwproto import MQTTTopic
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.property_format import SpaceheatName

from gwsproto.named_types import SingleMachineState
from pydantic import BaseModel
from pydantic import model_validator

from gwadmin.watch.clients.admin_client import type_name
from gwadmin.watch.clients.admin_client import AdminClient
from gwadmin.watch.clients.admin_client import AdminSubClient
from gwadmin.watch.clients.constrained_mqtt_client import MessageReceivedCallback
from gwadmin.watch.clients.constrained_mqtt_client import StateChangeCallback
from gwadmin.watch.clients.dispatch_replies import DispatchReply
from gwadmin.watch.clients.dispatch_replies import DispatchReplyTracker
from gwsproto.named_types import (AdminDispatch,  AdminKeepAlive, AdminReleaseControl,
                        CommandInterface, ScadaControlCapabilities, FsmEvent, SnapshotSpaceheat)

module_logger = logging.getLogger(__name__)

class CommandTransition(BaseModel):
    """One command a row takes and the state it leads to (gw.command.transition),
    with the event type it is sent under: a node may take commands from
    more than one vocabulary (five-v-boss takes turn.5v.on.off and
    reboot.picos)."""
    event_type: str
    event: str
    to_state: str

class RelayConfig(BaseModel):
    """One row of the panel: a node the scada reports state for, with the
    commands the operator may send it. A relay owned by an interior command
    node (hp-boss's ops relay, the cycler's vdc relay) has no commands and
    shows state only; the interior node's row carries the commands."""
    about_node_name: SpaceheatName
    owner: Optional[SpaceheatName] = None
    """The interior command node whose Handle this node's Handle extends
    by one segment; None for a node the operator commands directly."""
    channel_name: Optional[SpaceheatName] = None
    state_type: str
    commands: list[CommandTransition]

class RelayState(BaseModel):
    value: str
    """A value of the row's state_type enum, from single.machine.state."""
    time: int # unix ms

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
CtrlCapabilitiesCallback = Callable[[ScadaControlCapabilities], None]
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
DispatchReplyCallback = Callable[[DispatchReply], None]

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

    ctrl_capabilities_callback: Optional[CtrlCapabilitiesCallback] = None
    """Hook for user. Called when ScadaControlCapabilities received. Called from Paho thread. 
    Must be threadsafe."""

    snapshot_callback: Optional[SnapshotCallback] = None
    """Hook for user. Called when a snapshot received. Called from Paho thread. 
    Must be threadsafe."""

    dispatch_reply_callback: Optional[DispatchReplyCallback] = None
    """Hook for user. Called when the scada acks or nacks a dispatch. Called
    from Paho thread. Must be threadsafe."""

class RelayWatchClient(AdminSubClient):
    _lock: threading.RLock
    _relays: dict[SpaceheatName, RelayInfo]
    _admin_client: AdminClient
    _callbacks: RelayClientCallbacks
    _replies: DispatchReplyTracker
    _ctrl_capabilities: ScadaControlCapabilities | None = None
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
        self._replies = DispatchReplyTracker()

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
    def _get_relay_configs(cls, ctrl_capabilities: ScadaControlCapabilities) -> dict[str, RelayConfig]:
        """One row per relay and per interior command node. The commands are
        the union over the node's command interfaces (one per vocabulary,
        all reporting the same state type); a relay under an interior node
        has none (it is commanded through its owner) and its state_type is
        read off its owner-independent state channel name only for display."""
        interfaces: dict[str, list[CommandInterface]] = {}
        for i in ctrl_capabilities.CommandInterfaces:
            interfaces.setdefault(i.ActorName, []).append(i)
        channels = {c.AboutNodeName: c for c in ctrl_capabilities.ControlChannels}
        owners = {n.Handle: n.Name for n in ctrl_capabilities.CommandNodes}
        configs: dict[str, RelayConfig] = {}
        for node in ctrl_capabilities.RelayNodes + ctrl_capabilities.CommandNodes:
            node_interfaces = interfaces.get(node.Name, [])
            channel = channels.get(node.Name)
            boss_handle = node.Handle.rsplit(".", 1)[0] if node.Handle else ""
            configs[node.Name] = RelayConfig(
                about_node_name=node.Name,
                owner=owners.get(boss_handle),
                channel_name=channel.Name if channel is not None else None,
                state_type=node_interfaces[0].StateType if node_interfaces else "",
                commands=[
                    CommandTransition(event_type=i.EventType, event=c.Event, to_state=c.ToState)
                    for i in node_interfaces
                    for c in i.Commands
                ],
            )
        return configs

    def _update_ctrl_capabilities(self, new_ctrl_capabilities: ScadaControlCapabilities) -> dict[SpaceheatName, RelayConfigChange]:
        with self._lock:
            self._ctrl_capabilities = new_ctrl_capabilities.model_copy()
            new_relay_configs = self._get_relay_configs(self._ctrl_capabilities)
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
        return changed_configs

    def process_scada_control_capabilities(self, ctrl_capabilities: ScadaControlCapabilities) -> None:
        config_changes = self._update_ctrl_capabilities(ctrl_capabilities)
        if config_changes and self._callbacks.relay_config_change_callback is not None:
            self._callbacks.relay_config_change_callback(config_changes)
        if self._callbacks.ctrl_capabilities_callback is not None:
            self._callbacks.ctrl_capabilities_callback(ctrl_capabilities)
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

    def _extract_relay_states(self, states: Sequence[SingleMachineState]) -> dict[str, RelayState]:
        """A row's state is the single.machine.state whose MachineHandle ends
        in the row's node name; a relay's pin-level report (StateEnum
        relay.pin) is not the row's state and is skipped."""
        extracted = {}
        for sms in states:
            node_name = sms.MachineHandle.split(".")[-1]
            relay_info = self._relays.get(node_name)
            if relay_info is None:
                continue
            if relay_info.config.state_type and sms.StateEnum != relay_info.config.state_type:
                continue
            if not relay_info.config.state_type and sms.StateEnum == "relay.pin":
                continue
            extracted[node_name] = RelayState(value=sms.State, time=sms.UnixMs)
        return extracted

    def _process_single_machine_state(self, payload: bytes) -> None:
        if self._ctrl_capabilities is not None:
            self._handle_new_relay_states(
                self._extract_relay_states(
                    [GWMessage[SingleMachineState].model_validate_json(payload).Payload]
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
        if self._ctrl_capabilities is not None:
            self._handle_new_relay_states(
                self._extract_relay_states(snapshot.LatestStateList)
            )

    def process_mqtt_state_changed(self, old_state: str, new_state: str) -> None:
        if self._callbacks.mqtt_state_change_callback is not None:
            self._callbacks.mqtt_state_change_callback(old_state, new_state)

    def process_mqtt_message(self, topic: str, payload: bytes) -> None:
        decoded_topic = MQTTTopic.decode(topic)
        if decoded_topic.message_type == type_name(SingleMachineState):
            self._process_single_machine_state(payload)
        elif (reply := self._replies.match(topic, payload)) is not None:
            if self._callbacks.dispatch_reply_callback is not None:
                self._callbacks.dispatch_reply_callback(reply)
        if self._callbacks.mqtt_message_received_callback is not None:
            self._callbacks.mqtt_message_received_callback(topic, payload)

    def scada_selection_reset(self) -> None:
        self._ctrl_capabilities = None
        self._snap = None
        with self._lock:
            removed_relays = self._relays
            self._relays = {}
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

    def send_command(self, node_name: str, event: str, timeout_seconds: Optional[int] = None) -> None:
        """Send one of the row's commands to its node, in the node's own
        vocabulary: a relay event, TurnHpOnOff to hp-boss, RebootPicos to
        the pico-cycler. The node adopts the TriggerId, so its reply and its
        fsm.full.report carry it back."""
        self._send_command(node_name, event, datetime.datetime.now(), timeout_seconds)

    def _send_command(
            self,
            node_name: str,
            event_name: str,
            set_time: datetime.datetime,
            timeout_seconds: Optional[int] = None
    ) -> None:
        config = self._relays[node_name].config
        command = next((c for c in config.commands if c.event == event_name), None)
        if command is None:
            raise ValueError(f"{node_name} takes {[c.event for c in config.commands]}, not {event_name}")
        event = FsmEvent(
            FromHandle=H0N.admin,
            ToHandle=f"{H0N.admin}.{node_name}",
            EventType=command.event_type,
            EventName=event_name,
            SendTimeUnixMs=int(set_time.timestamp() * 1000),
            TriggerId=str(uuid.uuid4()),
        )
        self._replies.note(event.TriggerId, event.ToHandle, event_name)
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

