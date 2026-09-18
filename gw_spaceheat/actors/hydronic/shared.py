"""Family-neutral hydronic helpers — zone-call circuit relays, the vdc
pair, TOU/setpoint judgment, temperature access. Inherited by every
family's control impls and by PicoCycler (tier C+D shared slice of the
sh_node_actor partition; see the partition spoke)."""

import time
import uuid
from datetime import datetime, timedelta
from typing import Optional
from pydantic import ValidationError
from gwsproto.errors import DcError
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeZoneCallSource,
    ChangeRelayState,
)
from gwsproto.named_types import FsmEvent
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatZoneChannelNames as HSZoneChannelNames,
)
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatZoneNodeNames as HSZoneNodeNames,
)

from actors.command_node import CommandNode

class HydronicNode(CommandNode):
    """CommandNode + the family-neutral hydronic surface."""

    def zone_channels(self) -> list[HSZoneChannelNames]:
        """The layout's zones in order, as their hydronic-tier channel names."""
        return [HSZoneChannelNames(zone, i + 1) for i, zone in enumerate(self.layout.zone_list)]

    def refresh_setpoints_at_onpeak_start(self) -> None:
        """Take each layout zone's current setpoint (`zone{i}-{label}-set`,
        F x 1000, keyed by the zone channel base) as the setpoint the zone had
        when on-peak began. `is_system_cold` judges against the lower of this
        and the current setpoint, so a thermostat raised during on-peak does
        not read as a cold house. Refreshed off-peak; held through on-peak."""
        self.setpoints_at_onpeak_start = {}
        for zone in self.zone_channels():
            setpoint = self.data.latest_channel_values.get(zone.set)
            if setpoint is not None:
                self.setpoints_at_onpeak_start[zone.base] = setpoint

    def just_before_onpeak(self) -> bool:
        """Within the two minutes before an on-peak window opens."""
        time_now = datetime.now(self.timezone)
        return not self.in_onpeak_window(time_now) and self.in_onpeak_window(
            time_now + timedelta(minutes=2)
        )

    def is_onpeak(self) -> bool:
        """In an on-peak window, or within two minutes of one opening."""
        time_now = datetime.now(self.timezone)
        return self.in_onpeak_window(time_now) or self.in_onpeak_window(
            time_now + timedelta(minutes=2)
        )

    def is_system_cold(self) -> bool:
        """Returns True if at least one critical zone is more than 1F below setpoint.
        Setpoint used is the minimum of: (a) setpoint at start of on-peak, (b) current setpoint.
        Using (a) avoids triggering when the user raises the thermostat during on-peak; using the
        minimum with (b) avoids triggering when the user lowers the thermostat during on-peak."""
        if not self.is_onpeak():  # TODO: bleed into the first half hour of offpeak
            self.refresh_setpoints_at_onpeak_start()
        critical = set(self.layout.critical_zone_list)
        for i, zone_name in enumerate(self.layout.zone_list):
            if zone_name not in critical:
                continue
            zone_channels = HSZoneChannelNames(zone_name, i + 1)
            zone = zone_channels.base

            # Use the lower of setpoint at start of on-peak vs current setpoint
            setpoint_at_onpeak = self.setpoints_at_onpeak_start.get(zone)
            current_setpoint = self.data.latest_channel_values.get(zone_channels.set)
            if setpoint_at_onpeak is not None and current_setpoint is not None:
                setpoint = min(setpoint_at_onpeak, current_setpoint)
            elif setpoint_at_onpeak is not None:
                setpoint = setpoint_at_onpeak
            elif current_setpoint is not None:
                setpoint = current_setpoint
            else:
                self.log(f"Could not find setpoint for {zone}!")
                continue

            temperature = self.data.latest_channel_values.get(zone_channels.temp)
            if temperature is None:
                self.log(f"Could not find latest temperature for {zone}!")
                continue

            if temperature < setpoint - 1000:  # 1F in millidegrees
                self.log(
                    f"{zone} temperature is at least 1F lower than the effective setpoint "
                    "(min of on-peak start and current)"
                )
                return True
        self.log("All critical zones are at or above their effective setpoint")
        return False

    def close_vdc_relay(self, trigger_id: Optional[str] = None, from_node: Optional[ShNode] = None) -> None:
        """
        Close vdc relay (de-energizing relay 1).
        Will log an error and do nothing if not the boss of this relay
        """
        if trigger_id is None:
            trigger_id = str(uuid.uuid4())
        try:
            event = FsmEvent(
                FromHandle=self.node.handle if from_node is None else from_node.handle,
                ToHandle=self.layout.vdc_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=trigger_id,
            )
            self._send_to(self.layout.vdc_relay, event, from_node)
            self.log(f"CloseRelay to {self.layout.vdc_relay.name}")
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def open_vdc_relay(self, trigger_id: Optional[str] = None, from_node: Optional[ShNode] = None) -> None:
        """
        Open vdc relay (energizing relay 1).
        Will log an error and do nothing if not the boss of this relay
        """
        if trigger_id is None:
            trigger_id = str(uuid.uuid4())
        try:

            event = FsmEvent(
                FromHandle=self.node.handle if from_node is None else from_node.handle,
                ToHandle=self.layout.vdc_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=trigger_id,
            )
            self._send_to(self.layout.vdc_relay, event, from_node)
            self.log(f"OpenRelay to {self.layout.vdc_relay.name}")
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def stat_failsafe_relay(self, zone: str) -> ShNode:
        """
        Returns the failsafe relay for the zone.
        Raises a DcError if zone is not in the layout's zone_list
        """
        try:
            i = self.layout.zone_list.index(zone)
        except ValueError as e:
            raise DcError(
                f"Called stat_failsafe_relay for {zone} which does not exist!"
            ) from e
        return self.required_node(HSZoneNodeNames(zone, i + 1).failsafe_relay)

    def stat_ops_relay(self, zone: str) -> ShNode:
        """
        Returns the scada thermostat ops relay for the zone
        Raises a DcError if zone is not in the layout's zone_list
        """
        try:
            i = self.layout.zone_list.index(zone)
        except ValueError as e:
            raise DcError(
                f"Called stat_ops_relay for {zone} which does not exist!"
            ) from e
        return self.required_node(HSZoneNodeNames(zone, i + 1).ops_relay)

    def heatcall_ctrl_to_scada(self, zone: str, command_node: ShNode | None = None) -> None:
        """
        Take over thermostatic control of the zone from the wall thermostat
        by energizing appropriate relay.
        Will log an error and do nothing if not the boss of this relay.
        """
        if command_node is None:
            command_node = self.node
        if zone not in self.layout.zone_list:
            self.log(f"{zone} not a recongized zone!")
            return
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.stat_failsafe_relay(zone).handle,
                EventType=ChangeZoneCallSource.enum_name(),
                EventName=ChangeZoneCallSource.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )

            self._send_to(self.stat_failsafe_relay(zone), event, command_node)
            self.log(
                f"{command_node.handle} sending SwitchToScada to {self.stat_failsafe_relay(zone).handle} (zone {zone})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def heatcall_ctrl_to_stat(self, zone: str, command_node: ShNode| None = None) -> None:
        """
        Return control of the whitewire heatcall signal to the wall thermostat
        by de-energizing appropriate relay.

        If provided command_node is None, command_node defaults to self.node

        Will log an error and do nothing if not the boss of this relay.
        """
        if command_node is None:
            command_node = self.node
        if zone not in self.layout.zone_list:
            self.log(f"{zone} not a recongized zone!")
            return
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.stat_failsafe_relay(zone).handle,
                EventType=ChangeZoneCallSource.enum_name(),
                EventName=ChangeZoneCallSource.SwitchToWallThermostat,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_failsafe_relay(zone), event, command_node)
            self.log(
                f"{command_node.handle} sending SwitchToWallThermostat to {self.stat_failsafe_relay(zone).handle} (zone {zone})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def stat_ops_close_relay(self, zone: str, command_node: ShNode | None = None) -> None:
        """
        Close (energize) the ScadaOps relay for associated zone. Will send a heatcall on the white
        wire IF the associated failsafe relay is energized (switched to SCADA).
        Will log an error and do nothing if not the boss of this relay.
        """
        if command_node is None:
            command_node = self.node
        if zone not in self.layout.zone_list:
            self.log(f"{zone} not a recongized zone!")
            return
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.stat_ops_relay(zone).handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_ops_relay(zone), event, command_node)
            self.log(
                f"{command_node.handle} sending CloseRelay to {self.stat_ops_relay(zone).handle} (zone {zone})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def stat_ops_open_relay(self, zone: str, command_node: ShNode | None = None) -> None:
        """
        Open (de-energize) the ScadaOps relay for associated zone. Will send 0 on the white
        wire IF the associated failsafe relay is energized (switched to SCADA).
        Will log an error and do nothing if not the boss of this relay.
        """
        if command_node is None:
            command_node = self.node
        if zone not in self.layout.zone_list:
            self.log(f"{zone} not a recongized zone!")
            return
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.stat_ops_relay(zone).handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_ops_relay(zone), event, command_node)
            self.log(
                f"{command_node.handle} sending OpenRelay to {self.stat_ops_relay(zone).handle} (zone {zone})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    @property
    def latest_temps_f(self) -> dict[str, float]:
        return self.data.latest_temperatures_f


