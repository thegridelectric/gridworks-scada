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
from gwsproto.enums import ActorClass
from gwsproto.named_types import AnalogDispatch

from gwsproto.named_types import SingleReading
from pydantic import BaseModel
from pydantic import model_validator

from gwadmin.watch.clients.admin_client import type_name
from gwadmin.watch.clients.admin_client import AdminClient
from gwadmin.watch.clients.admin_client import AdminSubClient
from gwadmin.watch.clients.constrained_mqtt_client import MessageReceivedCallback
from gwadmin.watch.clients.constrained_mqtt_client import StateChangeCallback
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.named_types import AdminAnalogDispatch
from gwsproto.named_types import (AdminKeepAlive, AdminReleaseControl,
                         LayoutLite, SnapshotSpaceheat)

module_logger = logging.getLogger(__name__)

class DACConfig(BaseModel):
    about_node_name: str = ""
    channel_name: str = ""

class DACState(BaseModel):
    value: int
    time: datetime.datetime

class DACInfo(BaseModel):
    config: DACConfig
    observed: Optional[DACState] = None

class ObservedDACStateChange(BaseModel):
    old_state: Optional[DACState] = None
    new_state: Optional[DACState] = None

    @model_validator(mode="after")
    def _model_validator(self) -> Self:
        if self.old_state == self.new_state:
            raise ValueError(
                f"ERROR ObservedDACStateChange has no change: {self.old_state}"
            )
        return self

DACStateChangeCallback = Callable[[dict[str, ObservedDACStateChange]], None]
LayoutCallback = Callable[[LayoutLite], None]
SnapshotCallback = Callable[[SnapshotSpaceheat], None]

class DACConfigChange(BaseModel):
    old_config: Optional[DACConfig] = None
    new_config: Optional[DACConfig] = None

    @model_validator(mode="after")
    def _model_validator(self) -> Self:
        if self.old_config == self.new_config:
            raise ValueError(
                f"ERROR DACConfigChange has no change: {self.old_config}"
            )
        return self

DACConfigChangeCallback = Callable[[dict[str, DACConfigChange]], None]

@dataclass
class DACClientCallbacks:
    """Hooks for user of DACWatchClient. Must be threadsafe."""

    mqtt_state_change_callback: Optional[StateChangeCallback] = None
    """Hook for user. Called when mqtt client 'state'
    variable changes. Generally, but not exclusively, called from Paho thread.
    Must be threadsafe."""

    mqtt_message_received_callback: Optional[MessageReceivedCallback] = None
    """Hook for user. Called when an mqtt message is received if that message is 
     not DAC-related or 'pass_all_messages' is True. Called from Paho thread.
     Must be threadsafe."""

    dac_state_change_callback: Optional[DACStateChangeCallback] = None
    """Hook for user. Called when a DAC state change is observed. 
    Called from Paho thread. Must be threadsafe."""

    dac_config_change_callback: Optional[DACConfigChangeCallback] = None
    """Hook for user. Called when a DAC config change is observed. 
    Called from Paho thread. Must be threadsafe."""

    layout_callback: Optional[LayoutCallback] = None
    """Hook for user. Called when a layout received. Called from Paho thread. 
    Must be threadsafe."""

    snapshot_callback: Optional[SnapshotCallback] = None
    """Hook for user. Called when a snapshot received. Called from Paho thread. 
    Must be threadsafe."""

class DACWatchClient(AdminSubClient):
    _lock: threading.RLock
    _dacs: dict[str, DACInfo]
    _channel2node: dict[str, str]
    _pass_all_message: bool = False
    _admin_client: AdminClient
    _callbacks: DACClientCallbacks
    _layout: Optional[LayoutLite] = None
    _snap: Optional[SnapshotSpaceheat] = None
    _logger: Logger | logging.LoggerAdapter[Logger] = module_logger

    def __init__(
            self,
            callbacks: Optional[DACClientCallbacks] = None,
            *,
            pass_all_messages: bool = False,
            logger: Logger | logging.LoggerAdapter[Logger] = module_logger,
    ) -> None:
        self._lock = threading.RLock()
        self._callbacks = callbacks or DACClientCallbacks()
        self._logger = logger
        self._dacs = {}
        self._channel2node = {}
        self._pass_all_message = pass_all_messages

    def set_admin_client(self, client: AdminClient) -> None:
        self._admin_client = client

    def set_callbacks(self, callbacks: DACClientCallbacks) -> None:
        if self._admin_client.started():
            raise ValueError(
                "ERROR. AdminClient callbacks must be set before starting "
                "the client."
            )
        self._callbacks = callbacks

    @classmethod
    def _get_dac_configs(cls, layout: LayoutLite) -> dict[str, DACConfig]:
        dac_node_names = {node.Name for node in layout.ShNodes if node.ActorClass == ActorClass.ZeroTenOutputer}
        dac_channels = {channel.AboutNodeName: channel for channel in layout.DataChannels if channel.AboutNodeName in dac_node_names}
        return {
            node_name : DACConfig(
                about_node_name=node_name,
                channel_name=dac_channels[node_name].Name,
            ) for node_name in dac_node_names
        }

    def _update_layout(self, new_layout: LayoutLite) -> dict[str, DACConfigChange]:
        with self._lock:
            self._layout = new_layout.model_copy()
            new_dac_configs = self._get_dac_configs(self._layout)
            old_dac_names = set(self._dacs.keys())
            new_dac_names = set(new_dac_configs.keys())
            changed_configs = {}
            for added_dac_name in (new_dac_names - old_dac_names):
                self._dacs[added_dac_name] = DACInfo(
                    config=new_dac_configs[added_dac_name],
                )
                changed_configs[added_dac_name] = DACConfigChange(
                    old_config=None,
                    new_config=new_dac_configs[added_dac_name],
                )
            for removed_dac_name in (old_dac_names - new_dac_names):
                changed_configs[removed_dac_name] = DACConfigChange(
                    old_config=self._dacs.pop(removed_dac_name).config,
                    new_config=None,
                )
            for dac_name in new_dac_names.intersection(old_dac_names):
                new_config = new_dac_configs[dac_name]
                if new_config != self._dacs[dac_name].config:
                    changed_configs[dac_name] = DACConfigChange(
                        old_config=self._dacs[dac_name].config,
                        new_config=new_config,
                    )
                    self._dacs[dac_name].config = new_config
            if changed_configs:
                self._channel2node = {
                    DAC.config.channel_name: DAC.config.about_node_name
                    for DAC in self._dacs.values()
                }
        return changed_configs

    def process_layout_lite(self, layout: LayoutLite) -> None:
        config_changes = self._update_layout(layout)
        if config_changes and self._callbacks.dac_config_change_callback is not None:
            self._callbacks.dac_config_change_callback(config_changes)
        if self._callbacks.layout_callback is not None:
            self._callbacks.layout_callback(layout)
        if self._snap is not None:
           self._process_snapshot(self._snap)

    def _update_dac_states(self, new_states: dict[str, DACState]) -> dict[str, ObservedDACStateChange]:
        changes: dict[str, ObservedDACStateChange] = {}
        with self._lock:
            for dac_name, new_state in new_states.items():
                data_info = self._dacs.get(dac_name)
                if data_info is not None:
                    old_state = copy.deepcopy(data_info.observed)
                    if old_state != new_state:
                        if old_state is None or new_state.time > old_state.time:
                            data_info.observed = new_state
                            changes[dac_name] = ObservedDACStateChange(
                                old_state=old_state,
                                new_state=new_state,
                            )
        return changes

    def _handle_new_dac_states(self, new_states: dict[str, DACState]) -> None:
        state_changes = self._update_dac_states(new_states)
        if state_changes and self._callbacks.dac_state_change_callback is not None:
            self._callbacks.dac_state_change_callback(state_changes)

    def _dac_info_from_channel(self, channel_name: str) -> Optional[DACInfo]:
        return self._dacs.get(
            self._channel2node.get(channel_name, ""), None
        )

    def _extract_dac_states(self, readings: Sequence[SingleReading]) -> dict[str, DACState]:
        states = {}
        for reading in readings:
            if data_info := self._dac_info_from_channel(reading.ChannelName):
                states[data_info.config.about_node_name] = DACState(
                    value=reading.Value,
                    time=reading.ScadaReadTimeUnixMs,
                )
        return states

    def _process_single_reading(self, payload: bytes) -> None:
        if self._layout is not None:
            self._handle_new_dac_states(
                self._extract_dac_states(
                    [GWMessage[SingleReading].model_validate_json(payload).Payload]
                )
            )

    def process_snapshot(self, snapshot: SnapshotSpaceheat) -> None:
        # self._logger.debug("++DACWatchClient.process_snapshot")
        path_dbg = 0
        self._process_snapshot(snapshot)
        if self._callbacks.snapshot_callback is not None:
            path_dbg |= 0x0000001
            self._callbacks.snapshot_callback(snapshot)
        # self._logger.debug("--DACWatchClient.process_snapshot  path:0x%08X", path_dbg)

    def _process_snapshot(self, snapshot: SnapshotSpaceheat) -> None:
        if self._layout is not None:
            self._handle_new_dac_states(
                self._extract_dac_states(snapshot.LatestReadingList)
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

    def set_dac(self, dac_row_name: str, new_state: int, timeout_seconds: Optional[int] = None):
        self._send_set_command(dac_row_name, new_state, datetime.datetime.now(), timeout_seconds)

    def _send_set_command(
            self,
            dac_row_name: str,
            value: int,
            set_time: datetime.datetime,
            timeout_seconds: Optional[int] = None
    ) -> None:
        dac_node_name = dac_row_name.lower() + "-010v"
        self._admin_client.publish(
            AdminAnalogDispatch(
                Dispatch=AnalogDispatch(
                    FromGNodeAlias=None,
                    FromHandle=H0N.admin,
                    ToHandle=f"{H0N.admin}.{dac_node_name}",
                    AboutName=dac_node_name,
                    Value=value,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=int(set_time.timestamp() * 1000),
                ),
                TimeoutSeconds=timeout_seconds,
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

    def scada_selection_reset(self) -> None:
        self._layout = None
        self._snap = None
        with self._lock:
            removed_dacs = self._dacs
            self._dacs = {}
            self._channel2node = {}
        if removed_dacs and self._callbacks.dac_config_change_callback is not None:
            self._callbacks.dac_config_change_callback(
                {
                    dac_name: DACConfigChange(
                        old_config=dac.config,
                        new_config=None,
                    )
                    for dac_name, dac in removed_dacs.items()
                 }
            )
