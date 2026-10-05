"""Family-neutral hydronic helpers — zone-call circuit relays, the vdc
pair, TOU judgment, temperature access, whether the buffer and store
are empty. Inherited by every
family's control impls and by PicoCycler (tier C+D shared slice of the
sh_node_actor partition; see the partition spoke)."""

import time
import uuid
from datetime import datetime, timedelta
from typing import Optional
from pydantic import ValidationError
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeZoneCallSource,
    ChangeRelayState,
    TurnHpOnOff,
)
from gwsproto.named_types import FsmEvent, ZoneCallCircuit
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN

from actors.command_node import CommandNode

class HydronicNode(CommandNode):
    """CommandNode + the family-neutral hydronic surface."""

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

    @property
    def hp_boss(self) -> ShNode:
        return self.layout.hp_boss

    def turn_on_hp(self, from_node: Optional[ShNode] = None) -> None:
        """Tell hp-boss, the heat pump's command node, to turn the heat
        pump on. from_node defaults to self.node; the command is dropped
        with a log line if from_node is not hp-boss's boss."""
        self.send_state_command(self.hp_boss, TurnHpOnOff.TurnOn, from_node)

    def turn_off_hp(self, from_node: Optional[ShNode] = None) -> None:
        """Tell hp-boss to turn the heat pump off (see turn_on_hp)."""
        self.send_state_command(self.hp_boss, TurnHpOnOff.TurnOff, from_node)

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

    def stat_failsafe_relay(self, circuit: ZoneCallCircuit) -> ShNode:
        """Returns the circuit's failsafe relay."""
        return self.required_node(circuit.FailsafeRelayNode)

    def stat_ops_relay(self, circuit: ZoneCallCircuit) -> ShNode:
        """Returns the circuit's scada thermostat ops relay."""
        return self.required_node(circuit.OpsRelayNode)

    def heatcall_ctrl_to_scada(self, circuit: ZoneCallCircuit, command_node: ShNode | None = None) -> None:
        """
        Take over thermostatic control of the circuit from the wall thermostat
        by energizing appropriate relay.
        Will log an error and do nothing if not the boss of this relay.
        """
        if command_node is None:
            command_node = self.node
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.stat_failsafe_relay(circuit).handle,
                EventType=ChangeZoneCallSource.enum_name(),
                EventName=ChangeZoneCallSource.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )

            self._send_to(self.stat_failsafe_relay(circuit), event, command_node)
            self.log(
                f"{command_node.handle} sending SwitchToScada to {self.stat_failsafe_relay(circuit).handle} (circuit {circuit.Name})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def heatcall_ctrl_to_stat(self, circuit: ZoneCallCircuit, command_node: ShNode| None = None) -> None:
        """
        Return control of the whitewire heatcall signal to the wall thermostat
        by de-energizing appropriate relay.

        If provided command_node is None, command_node defaults to self.node

        Will log an error and do nothing if not the boss of this relay.
        """
        if command_node is None:
            command_node = self.node
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.stat_failsafe_relay(circuit).handle,
                EventType=ChangeZoneCallSource.enum_name(),
                EventName=ChangeZoneCallSource.SwitchToWallThermostat,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_failsafe_relay(circuit), event, command_node)
            self.log(
                f"{command_node.handle} sending SwitchToWallThermostat to {self.stat_failsafe_relay(circuit).handle} (circuit {circuit.Name})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def stat_ops_close_relay(self, circuit: ZoneCallCircuit, command_node: ShNode | None = None) -> None:
        """
        Close (energize) the ScadaOps relay for the circuit. Will send a heatcall on the white
        wire IF the associated failsafe relay is energized (switched to SCADA).
        Will log an error and do nothing if not the boss of this relay.
        """
        if command_node is None:
            command_node = self.node
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.stat_ops_relay(circuit).handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_ops_relay(circuit), event, command_node)
            self.log(
                f"{command_node.handle} sending CloseRelay to {self.stat_ops_relay(circuit).handle} (circuit {circuit.Name})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def stat_ops_open_relay(self, circuit: ZoneCallCircuit, command_node: ShNode | None = None) -> None:
        """
        Open (de-energize) the ScadaOps relay for the circuit. Will send 0 on the white
        wire IF the associated failsafe relay is energized (switched to SCADA).
        Will log an error and do nothing if not the boss of this relay.
        """
        if command_node is None:
            command_node = self.node
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.stat_ops_relay(circuit).handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_ops_relay(circuit), event, command_node)
            self.log(
                f"{command_node.handle} sending OpenRelay to {self.stat_ops_relay(circuit).handle} (circuit {circuit.Name})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def is_buffer_empty(self, all_tanks_leaf_ally=False) -> bool:
        """
        Returns True if the buffer does not contain enough usable heat
        to meet the near-term required return-water temperature.

        Uses the coldest available top-of-buffer measurement and the
        maximum required RWT minus delta-T over the next few hours.

        If forecasts are unavailable, returns False (cannot assert empty).
        """

        # Select the best available "top of buffer" temperature channel
        if all_tanks_leaf_ally and self.ops.FamilyParams.KeepBufferFull and HCN.buffer.depth3 in self.data.latest_temperatures_f:
            buffer_empty_ch = HCN.buffer.depth3
        elif HCN.buffer.depth1 in self.data.latest_temperatures_f:
            buffer_empty_ch = HCN.buffer.depth1
        elif HCN.dist_swt in self.data.latest_temperatures_f:
            buffer_empty_ch = HCN.dist_swt
        else:
            # No meaningful buffer temperature available
            self.log("is_buffer_empty: no buffer temperature channel available")
            return False

        if self.heating_forecast is None:
            # Cannot reason about emptiness without forecast context
            self.log("is_buffer_empty: no heating forecast available")
            return False

        # Conservative near-term requirement (next ~3 hours)
        max_rswt = max(self.heating_forecast.RswtF[:3])
        max_delta_t = max(self.heating_forecast.RswtDeltaTF[:3])
        if all_tanks_leaf_ally and self.ops.FamilyParams.KeepBufferFull:
            min_buffer_temp_f = round(max_rswt - max_delta_t, 1)
        else:
            min_buffer_temp_f = round(max_rswt, 1)

        min_buffer_temp_f = min(min_buffer_temp_f, self.data.ha1_params.MaxEwtF-10)
        buffer_temp_f = self.data.latest_temperatures_f[buffer_empty_ch]

        if buffer_temp_f < min_buffer_temp_f:
            self.log(
                f"Buffer empty ({buffer_empty_ch}: {buffer_temp_f} < {min_buffer_temp_f} F), RSWT is {max_rswt}F"
            )
            return True
        else:
            self.log(
                f"Buffer not empty ({buffer_empty_ch}: {buffer_temp_f} >= {min_buffer_temp_f} F), RSWT is {max_rswt}F"
            )
            return False

    def is_storage_empty(self):
        if self.usable_kwh < 0.2:
            return True
        else:
            return False

    @property
    def usable_kwh(self) -> float:
        """
        Latest usable thermal energy in kWh, derived from SCADA channel.
        Returns 0 if not yet available.
        """
        val =  self.data.latest_channel_values.get(HCN.usable_energy, 0)
        if val is None:
            val = 0
        return val / 1000
