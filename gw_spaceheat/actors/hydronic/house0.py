"""House0 hydronic knowledge: actuation choreography (HP, store valve,
pumps, aquastat, sieg, tstat common, 0-10V defaults) and plant judgment
(buffer/storage state, defrost). Inherited ONLY by House0 control impls.
Moved verbatim from sh_node_actor.py (partition spoke); upgrades land
separately."""

import time
import uuid
from typing import cast, Optional
from pydantic import ValidationError
from gwsproto.conversions.temperature import convert_temp_to_f
from gwsproto.data_classes.house_0_names import H0CN
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.data_classes.components.dfr_component import DfrComponent
from gwsproto.enums import (
    ActorClass,
    ChangeAquastatControl,
    ChangeHeatPumpControl,
    ChangeKeepSend,
    ChangePrimaryPumpControl,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    HpModel,
    StoreFlowRelay,
    TelemetryName,
    TurnHpOnOff
)
from gwsproto.named_types import AnalogDispatch, FsmEvent, SingleMachineState
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)
from actors.hydronic.shared import HydronicNode

class House0Hydronic(HydronicNode):
    """The House0 plant surface."""

    def close_tstat_common_relay(self, from_node: Optional[ShNode] = None) -> None:
        """
        Close tstat common relay (de-energizing relay 2).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.tstat_common_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.tstat_common_relay, event, from_node)
            self.log(f"{from_node.handle} sending CloseRelay to {self.layout.tstat_common_relay.handle}")
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def open_tstat_common_relay(self, from_node: Optional[ShNode] = None) -> None:
        """
        Open tstat common relay (energizing relay 2).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.tstat_common_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.tstat_common_relay, event, from_node)
            self.log(f"{from_node.handle} sending OpenRelay to {self.layout.tstat_common_relay.handle}")
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def valved_to_discharge_store(self, from_node: Optional[ShNode] = None) -> None:
        """
        Set valves to discharge store (de-energizing) store_charge_discharge_relay (3).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.store_charge_discharge_relay.handle,
                EventType=ChangeStoreFlowRelay.enum_name(),
                EventName=ChangeStoreFlowRelay.DischargeStore,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.store_charge_discharge_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending DischargeStore to Store ChargeDischarge {self.layout.store_charge_discharge_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change the charge/discharge store relay but didn't have the rights: {e}")

    def valved_to_charge_store(self, from_node: Optional[ShNode] = None) -> None:
        """
        Set valves to charge store (energizing) store_charge_discharge_relay (3).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.store_charge_discharge_relay.handle,
                EventType=ChangeStoreFlowRelay.enum_name(),
                EventName=ChangeStoreFlowRelay.ChargeStore,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.store_charge_discharge_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending ChargeStore to Store ChargeDischarge {self.layout.store_charge_discharge_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def hp_failsafe_switch_to_aquastat(self, from_node: Optional[ShNode] = None) -> None:
        """
        Set the hp control to Aquastat by de-energizing hp_failsafe_relay (5)
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.hp_failsafe_relay.handle,
                EventType=ChangeHeatPumpControl.enum_name(),
                EventName=ChangeHeatPumpControl.SwitchToTankAquastat,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.hp_failsafe_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToTankAquastat to Hp Failsafe {self.layout.hp_failsafe_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def hp_failsafe_switch_to_scada(self, from_node: Optional[ShNode] = None) -> None:
        """
        Set the hp control to Scada by energizing hp_failsafe_relay (5)
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.hp_failsafe_relay.handle,
                EventType=ChangeHeatPumpControl.enum_name(),
                EventName=ChangeHeatPumpControl.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.hp_failsafe_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToScada to Hp Failsafe {self.layout.hp_failsafe_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def turn_on_HP(self, from_node: Optional[ShNode] = None) -> None:
        """ Turn on heat pump

        """
        if from_node is None:
            from_node = self.node

        if self.data.use_sieg_loop:
            try:
                event = FsmEvent(
                    FromHandle=from_node.handle,
                    ToHandle=self.hp_boss.handle,
                    EventType=TurnHpOnOff.enum_name(),
                    EventName=TurnHpOnOff.TurnOn,
                    SendTimeUnixMs=int(time.time() * 1000),
                    TriggerId=str(uuid.uuid4()),
                )
                self._send_to(self.hp_boss, event, from_node)
                self.log(f"{from_node.handle} sending TurnOn to HpBoss {self.hp_boss.handle}")
            except ValidationError as e:
                self.log(f"Tried to tell HpBoss to turn on HP but didn't have rights: {e}")

        else:
            try:
                event = FsmEvent(
                    FromHandle=from_node.handle,
                    ToHandle=self.layout.hp_scada_ops_relay.handle,
                    EventType=ChangeRelayState.enum_name(),
                    EventName=ChangeRelayState.CloseRelay,
                    SendTimeUnixMs=int(time.time() * 1000),
                    TriggerId=str(uuid.uuid4()),
                )
                self._send_to(self.layout.hp_scada_ops_relay, event, from_node)
                self.log(f"{from_node.handle} sending CloseRelay to HpScadaOpsRelay {self.layout.hp_scada_ops_relay.handle}")
            except ValidationError as e:
                self.log(f"Tried to tell HpScadaOpsRelay to turn on HP but didn't have rights: {e}")

    def turn_off_HP(self, from_node: Optional[ShNode] = None) -> None:
        """  Turn off heat pump by sending trigger to HpRelayBoss
        
        from_node defaults to self.node if no from_node sent.
        Will log an error and do nothing if from_node is not the boss of HpRelayBoss
        """
        if from_node is None:
            from_node = self.node

        if self.data.use_sieg_loop:
            try:
                event = FsmEvent(
                    FromHandle=from_node.handle,
                    ToHandle=self.hp_boss.handle,
                    EventType=TurnHpOnOff.enum_name(),
                    EventName=TurnHpOnOff.TurnOff,
                    SendTimeUnixMs=int(time.time() * 1000),
                    TriggerId=str(uuid.uuid4()),
                )
                self._send_to(self.hp_boss, event, from_node)
                self.log(f"{from_node.handle} sending TurnOff to HpBoss {self.hp_boss.handle}")
            except ValidationError as e:
                self.log(f"Tried to tell HpBoss to turn off HP but didn't have rights: {e}")
        else:
            try:
                event = FsmEvent(
                    FromHandle=from_node.handle,
                    ToHandle=self.layout.hp_scada_ops_relay.handle,
                    EventType=ChangeRelayState.enum_name(),
                    EventName=ChangeRelayState.OpenRelay,
                    SendTimeUnixMs=int(time.time() * 1000),
                    TriggerId=str(uuid.uuid4()),
                )
                self._send_to(self.layout.hp_scada_ops_relay, event, from_node)
                self.log(
                    f"{from_node.handle} sending OpenRelay to HpScadaOpsRelay {self.layout.hp_scada_ops_relay.handle}"
                )
            except ValidationError as e:
                self.log(f"Tried to tell HpScadaOpsRelay to turn off HP but didn't have rights: {e}")

    def aquastat_ctrl_switch_to_boiler(self, from_node: Optional[ShNode] = None) -> None:
        """
        Switch Aquastat ctrl from Scada to boiler by de-energizing aquastat_control_relay (8).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.aquastat_control_relay.handle,
                EventType=ChangeAquastatControl.enum_name(),
                EventName=ChangeAquastatControl.SwitchToBoiler,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.aquastat_control_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToBoiler to Boiler Ctrl {self.layout.aquastat_control_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def aquastat_ctrl_switch_to_scada(self, from_node: Optional[ShNode] = None) -> None:
        """
        Switch Aquastat ctrl from boiler to Scada by energizing aquastat_control_relay (8).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.aquastat_control_relay.handle,
                EventType=ChangeAquastatControl.enum_name(),
                EventName=ChangeAquastatControl.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.aquastat_control_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToScada to Aquastat Ctrl {self.layout.aquastat_control_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def turn_off_store_pump(self, command_node: ShNode | None = None) -> None:
        """
        Turn off the store pump by opening (de-energizing) the store pump relay.
        Will log an error and do nothing if not the boss of this relay
        """
        if command_node is None:
            command_node = self.node
        try:
            event = FsmEvent(
                FromHandle=self.node.handle if command_node is None else command_node.handle,
                ToHandle=self.layout.store_pump_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.store_pump_relay, event, command_node)
            self.log(
                f"{command_node.handle} sending OpenRelay to StorePump OnOff {self.layout.store_pump_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def turn_on_store_pump(self, command_node:  ShNode | None = None) -> None:
        """
        Turn on the store pump by closing (energizing) the store pump relay.
        Will log an error and do nothing if not the boss of this relay
        """
        if command_node is None:
            command_node = self.node
        try:
            event = FsmEvent(
                FromHandle=command_node.handle,
                ToHandle=self.layout.store_pump_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.store_pump_relay, event, command_node)
            self.log(
                f"{self.node.handle if command_node is None else command_node.handle} sending CloseRelay to StorePump OnOff {self.layout.store_pump_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def primary_pump_failsafe_to_hp(self, from_node: Optional[ShNode] = None) -> None:
        """
        Set heat pump to having direct control over primary pump by de-energizing
        primary_pump_failsafe_relay (12).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.primary_pump_failsafe.handle,
                EventType=ChangePrimaryPumpControl.enum_name(),
                EventName=ChangePrimaryPumpControl.SwitchToHeatPump,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.primary_pump_failsafe, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToHeatPump to {self.layout.primary_pump_failsafe.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def primary_pump_failsafe_to_scada(self, from_node: Optional[ShNode] = None) -> None:
        """
        Set Scada to having direct control over primary pump by energizing
        primary_pump_failsafe_relay (12).
        Will log an error and do nothing if not the boss of this relay.
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.primary_pump_failsafe.handle,
                EventType=ChangePrimaryPumpControl.enum_name(),
                EventName=ChangePrimaryPumpControl.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.primary_pump_failsafe, event, from_node)
            self.log(
                f"{self.node.handle if from_node is None else from_node.handle} sending SwitchToHeatPump to {self.layout.primary_pump_failsafe.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def turn_off_primary_pump(self, from_node: Optional[ShNode] = None) -> None:
        """
        Turn off primary pump (if under Scada control) by de-energizing
        primary_pump_scada_ops (11).
        Will log an error and do nothing if not the boss of this relay.
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.primary_pump_scada_ops.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.primary_pump_scada_ops, event, from_node)
            self.log(
                f"{self.node.handle if from_node is None else from_node.handle} sending OpenRelay to {self.layout.primary_pump_scada_ops.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def turn_on_primary_pump(self, from_node: Optional[ShNode] = None) -> None:
        """
        Turn on primary pump (if under Scada control) by energizing
        primary_pump_scada_ops (11).
        Will log an error and do nothing if not the boss of this relay.
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.primary_pump_scada_ops.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.primary_pump_scada_ops, event, from_node)
            self.log(
                f"{self.node.handle if from_node is None else from_node.handle} sending CloseRelay to {self.layout.primary_pump_scada_ops.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def sieg_valve_active(self, from_node: Optional[ShNode] = None) -> None:
        """
        Activate the valve controlling how much water is flowing out of the
        Siegenthaler loop. This will result in the flow out beginning to decrease
        if relay 15 is in SendLess position, or beginning to increase if relay 15
        is in the SendMore position. De-energized state
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.hp_loop_on_off.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.hp_loop_on_off, event, from_node)
            self.log(
                f"{from_node.handle} sending CloseRelay to HpLoopOnOff relay {self.layout.hp_loop_on_off.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def sieg_valve_dormant(self, from_node: Optional[ShNode] = None) -> None:
        """
        Stop sending a signal to move the valve controlling how much water is 
        flowing out of the Siegenthaler loop.  Energized state.
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.hp_loop_on_off.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.hp_loop_on_off, event, from_node)
            self.log(
                f"{from_node.handle} sending OpenRelay to HpLoopOnOff relay {self.layout.hp_loop_on_off.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def change_to_hp_keep_less(self, from_node: Optional[ShNode] = None) -> None:
        """
        Sets the Keep/Send relay so that if relay 14 is On, the Siegenthaler
        valve moves towards sending MORE water out of the Siegenthaler loop (SendMore)
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.hp_loop_keep_send.handle,
                EventType=ChangeKeepSend.enum_name(),
                EventName=ChangeKeepSend.ChangeToKeepLess,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.hp_loop_keep_send, event, from_node)
            self.log(
                f"{from_node.handle} sending SendMore to HpLoopKeepSend relay {self.layout.hp_loop_keep_send.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def change_to_hp_keep_more(self, from_node: Optional[ShNode] = None) -> None:
        """
        Sets the Keep/Send relay so that if relay 15 is On, the Siegenthaler
        valve moves towards sending LESS water out of the Siegenthaler loop (SendLess)
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.layout.hp_loop_keep_send.handle,
                EventType=ChangeKeepSend.enum_name(),
                EventName=ChangeKeepSend.ChangeToKeepMore,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.layout.hp_loop_keep_send, event, from_node)
            self.log(
                f"{from_node.handle} sending SendLessto HpLoopKeepSend relay {self.layout.hp_loop_keep_send.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def set_010_defaults(self, command_node: ShNode | None = None) -> None:
        """
        Sets default 0-10V values for those actuators that are direct reports
        of the h.n (home alone normal node).
        """
        if command_node is None:
            command_node = self.node

        dfr_component = cast(DfrComponent, self.layout.node(House0NodeNames.zero_ten_out_multiplexer).component)
        commanded_010s = {
            node
            for node in self.my_actuators()
            if node.ActorClass == ActorClass.ZeroTenOutputer and
            self.the_boss_of(node) == command_node
        }

        for dfr_node in commanded_010s:
            dfr_config = next(
                    config
                    for config in dfr_component.gt.ConfigList
                    if config.ChannelName == dfr_node.name
                )
            self._send_to(
                dst=dfr_node,
                payload=AnalogDispatch(
                    FromGNodeAlias=self.layout.scada_g_node_alias,
                    FromHandle=command_node.handle,
                    ToHandle=dfr_node.handle,
                    AboutName=dfr_node.Name,
                    Value=dfr_config.InitialVoltsTimes100,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=int(time.time() * 1000),
                ),
                src=command_node
            )
            self.log(f"Just set {dfr_node.handle} to {dfr_config.InitialVoltsTimes100} from {command_node.handle} ")

    @property
    def hp_boss(self) -> ShNode:
        if not self.data.use_sieg_loop:
            raise Exception("Should not be calling for hp_boss if not using sieg loop")
        return self.layout.hp_boss

    @property
    def sieg_loop(self) -> ShNode:
        if not self.data.use_sieg_loop:
            raise Exception("Should not be calling for sieg_loop if not using sieg loop")
        return self.layout.node(HSNN.sieg_loop)

    @property
    def dist_010v(self) -> ShNode:
        return self.layout.dist_010v

    @property
    def store_010v(self) -> ShNode:
        return self.layout.store_010v

    @property
    def primary_010v(self) -> ShNode:
        return self.layout.primary_010v

    def discharging_store(self) -> bool:
        """
        Returns True if the system is actively discharging the store:
        - the charge/discharge relay is set to DischargingStore
        - and the store pump is moving water above threshold
        """
        relay_state: SingleMachineState = self.data.latest_machine_state.get(
            self.layout.store_charge_discharge_relay.name
        )

        if relay_state.State != StoreFlowRelay.DischargingStore:
            return False

        store_flow = self.data.latest_channel_values.get(H0CN.store_flow) or 0

        return store_flow > self.PUMP_FLOW_GPM_THRESHOLD * 100

    def flowing_from_hp_to_house(self) -> bool:
        """
        Returns True if the water is flowing from heat pump to buffer/dist

        Conditions:
        - charge/discharge relay is set to DischargingStore
        - primary pump is moving water above threshold
        - Store is not being charged
        """
        relay_state: SingleMachineState = self.data.latest_machine_state.get(
            self.layout.store_charge_discharge_relay.name
        )
        if relay_state.State != StoreFlowRelay.DischargingStore:
            return False

        primary_flow = self.data.latest_channel_values.get(H0CN.primary_flow) or 0
        return primary_flow > self.PUMP_FLOW_GPM_THRESHOLD * 100

    def odu_pwr(self) -> Optional[float]:
        """Returns the latest Heat Pump outdoor unit power in Watts, or None
        if it does not exist"""
        odu_pwr_channel = self.layout.channel(H0CN.hp_odu_pwr)
        assert odu_pwr_channel.TelemetryName == TelemetryName.PowerW
        return self.data.latest_channel_values.get(H0CN.hp_odu_pwr)

    def idu_pwr(self) -> Optional[float]:
        """Returns the latest Heat Pump indoor unit power in Watts, or None
        if it does not exist"""
        idu_pwr_channel = self.layout.channel(H0CN.hp_idu_pwr)
        assert idu_pwr_channel.TelemetryName == TelemetryName.PowerW
        return self.data.latest_channel_values.get(H0CN.hp_idu_pwr)

    def hp_in_defrost(self) -> bool:
        odu = self.odu_pwr()
        idu = self.idu_pwr()
        if odu is None or idu is None:
            return False
        hp_model = self.settings.hp_model
        if hp_model in (HpModel.SamsungFourTonneHydroKit, HpModel.SamsungFiveTonneHydroKit):
            return idu < 4000
        elif hp_model == HpModel.LgHighTempHydroKitPlusMultiV:
            return odu + idu < 8400
        return False

    def is_buffer_empty(self, all_tanks_leaf_ally=False) -> bool:
        """
        Returns True if the buffer does not contain enough usable heat
        to meet the near-term required return-water temperature.

        Uses the coldest available top-of-buffer measurement and the
        maximum required RWT minus delta-T over the next few hours.

        If forecasts are unavailable, returns False (cannot assert empty).
        """

        # Select the best available "top of buffer" temperature channel
        if all_tanks_leaf_ally and self.ops.ShortCycleBuffer and H0CN.buffer.depth3 in self.latest_temps_f:
            buffer_empty_ch = H0CN.buffer.depth3
        elif H0CN.buffer.depth1 in self.latest_temps_f:
            buffer_empty_ch = H0CN.buffer.depth1
        elif H0CN.dist_swt in self.latest_temps_f:
            buffer_empty_ch = H0CN.dist_swt
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
        if all_tanks_leaf_ally and self.ops.ShortCycleBuffer:
            min_buffer_temp_f = round(max_rswt - max_delta_t, 1)
        else:
            min_buffer_temp_f = round(max_rswt, 1)

        min_buffer_temp_f = min(min_buffer_temp_f, self.data.ha1_params.MaxEwtF-10)
        buffer_temp_f = self.latest_temps_f[buffer_empty_ch]

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

    def is_buffer_full(self) -> bool:
        """
        Returns True if the buffer is considered thermally full relative to
        near-term heating requirements.

        Prefers the coldest buffer layer (depth3) as the authoritative signal.
        If unavailable, may infer buffer fullness from proxy temperatures
        (e.g. buffer cold pipe or store cold pipe while discharging), emitting
        an informational glitch when doing so.
        """
        used_proxy: bool = True

        if H0CN.buffer.depth3 in self.latest_temps_f:
            buffer_full_ch = H0CN.buffer.depth3
            used_proxy = False
        elif H0CN.buffer_cold_pipe in self.latest_temps_f: # Note: often not even installed
            buffer_full_ch = H0CN.buffer_cold_pipe

        elif (
            self.discharging_store()
            and H0CN.store_cold_pipe in self.latest_temps_f
        ):
            buffer_full_ch = H0CN.store_cold_pipe
        elif (
            self.flowing_from_hp_to_house()
            and H0CN.hp_ewt in self.latest_temps_f
        ):
            buffer_full_ch = H0CN.hp_ewt
        else:
            return False

        if used_proxy:
            self.send_info(
                summary="Buffer full inferred from proxy temperature",
                details=(
                    f"Depth3 unavailable; using {used_proxy} "
                    f"({buffer_full_ch}) to infer buffer-full state."
                ),
            )

        if self.heating_forecast is None:
            max_buffer = self.data.ha1_params.MaxEwtF
            max_rswt = 0
        else:
            max_rswt = round(max(self.heating_forecast.RswtF[:3]), 1)
            max_buffer = min(max_rswt, self.data.ha1_params.MaxEwtF)

        buffer_full_ch_temp = self.latest_temps_f[buffer_full_ch]
        if buffer_full_ch_temp > max_buffer:
            self.log(
                f"Buffer full ({buffer_full_ch}: {buffer_full_ch_temp} > {max_buffer} F), RSWT is {max_rswt} F"
            )
            return True
        else:
            self.log(
                f"Buffer not full ({buffer_full_ch}: {buffer_full_ch_temp} <= {max_buffer} F), RSWT is {max_rswt} F"
            )
            return False


    def is_buffer_charge_limited(self) -> bool:
        """
        Returns True if the buffer cannot accept more heat without exceeding MaxEwtF.
        This is a physical limit.
        """
        if H0CN.hp_ewt in self.latest_temps_f and self.flowing_from_hp_to_house():
            channel_used = H0CN.hp_ewt
        elif H0CN.buffer_cold_pipe in self.latest_temps_f:
            channel_used = H0CN.buffer_cold_pipe
        elif H0CN.buffer.depth3 in self.latest_temps_f:
            channel_used = H0CN.buffer.depth3
        else:
            return False

        if self.latest_temps_f[channel_used] >= self.data.ha1_params.MaxEwtF:
            self.log(f"{channel_used}: {self.latest_temps_f[channel_used]} F >= {self.data.ha1_params.MaxEwtF} F")
            return True
        else:
            self.log(f"{channel_used}: {self.latest_temps_f[channel_used]} F < {self.data.ha1_params.MaxEwtF} F")
            return False

    def is_storage_colder_than_buffer(self, min_delta_f: float = 5.4, all_tanks_leaf_ally: bool = False) -> bool:
        """
        Returns True if the top of the storage is at least `min_delta_f` colder
        than the top of the buffer.
        If all_tanks_leaf_ally is True, uses the depth3 layer of the buffer instead.

        Pure physical predicate:
        - Returns False if required temperatures are unavailable
        """
        # --- Determine buffer top ---
        if H0CN.buffer.depth1 in self.latest_temps_f:
            buffer_top = H0CN.buffer.depth1
        elif H0CN.buffer.depth2 in self.latest_temps_f:
            buffer_top = H0CN.buffer.depth2
        elif H0CN.buffer.depth3 in self.latest_temps_f:
            buffer_top = H0CN.buffer.depth3
        elif H0CN.buffer_cold_pipe in self.latest_temps_f:
            buffer_top = H0CN.buffer_cold_pipe
        elif not all_tanks_leaf_ally or not self.ops.ShortCycleBuffer:
            return False

        # --- Determine storage top ---
        if self.h0cn.tank and self.h0cn.tank[1].depth1 in self.latest_temps_f:
            tank_top = self.h0cn.tank[1].depth1
        elif H0CN.store_hot_pipe in self.latest_temps_f:
            tank_top = H0CN.store_hot_pipe
        elif H0CN.buffer_hot_pipe in self.latest_temps_f:
            tank_top = H0CN.buffer_hot_pipe
        else:
            return False

        # --- Determine buffer bottom ---
        if all_tanks_leaf_ally and self.ops.ShortCycleBuffer:
            if H0CN.buffer.depth3 in self.latest_temps_f:
                buffer_bottom = H0CN.buffer.depth3
            elif H0CN.buffer.depth2 in self.latest_temps_f:
                buffer_bottom = H0CN.buffer.depth2
            elif H0CN.buffer.depth1 in self.latest_temps_f:
                buffer_bottom = H0CN.buffer.depth1
            else:
                return False
            return self.latest_temps_f[buffer_bottom] > self.latest_temps_f[tank_top]

        return self.latest_temps_f[buffer_top] > self.latest_temps_f[tank_top] + min_delta_f

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
        val =  self.data.latest_channel_values.get(H0CN.usable_energy, 0)
        if val is None:
            val = 0
        return val / 1000

    @property
    def required_kwh(self) -> float:
        """
        Latest required thermal energy in kWh, derived from SCADA channel.
        Returns 0 if not yet available.
        """
        val = self.data.latest_channel_values.get(H0CN.required_energy, 0)
        if val is None:
            val = 0
        return  val / 1000

    def fill_missing_store_temps(self):
        """
        Assumes stratified tank; missing layers are filled from colder layers below,
        using store_cold_pipe or a minimum plausible temperature as baseline.
        """
        all_store_layers = []
        for tank_idx in sorted(self.h0cn.tank):
            tank = self.h0cn.tank[tank_idx]
            all_store_layers.extend([tank.depth1, tank.depth2, tank.depth3])

        # TODO: raise WarningGlitch for temp > MAX_VALID_TANK_TEMP_F
        for layer in all_store_layers:
            value = self.data.latest_temperatures_f.get(layer)
            if (
                value is None
                or value < self.MIN_USED_TANK_TEMP_F
                or value > self.MAX_VALID_TANK_TEMP_F
            ):
                self.data.latest_temperatures_f.pop(layer, None)

        value_below = self.data.latest_temperatures_f.get(
            self.h0cn.store_cold_pipe,
            self.MIN_USED_TANK_TEMP_F,
        )

        for layer in reversed(all_store_layers):
            if layer not in self.data.latest_temperatures_f:
                self.data.latest_temperatures_f[layer] = value_below
            value_below = self.data.latest_temperatures_f[layer]

    def get_temperatures(self) -> None:
        """
        1. Updates data.latest_temperatures_f with data from latest_channel_values
        2. Updates buffer_available state
        3. May fill tank temperatures (not buffer) if some are missing and can be
           interpolated
        """

        temps: dict[str, float] = {}

        for ch_name in self.temperature_channel_names:
            raw = self.data.latest_channel_values.get(ch_name)
            if raw is None:
                continue

            try:
                unit = self.layout.channel_registry.unit(ch_name)
                if unit is None:
                    raise Exception(
                        f"temperature channels should have units! {ch_name}"
                    )
                temp_f = convert_temp_to_f(
                    raw=raw,
                    encoding=unit
                )
            except Exception as e:
                note = f"Temperature conversion failed for {ch_name}: {e}"
                self.log(note)
                self.send_warning(summary=note, details="")  
                continue
            if temp_f is None:
                continue

            temps[ch_name] = round(temp_f, 1)

        self.data.latest_temperatures_f = temps

        # Update buffer_available
        self.data.buffer_temps_available = (
            self.h0cn.buffer.effective <= self.data.latest_temperatures_f.keys()
        )

        tank_temps = set().union(
            *(tank.effective for tank in self.h0cn.tank.values())
        )

        if not (tank_temps <= self.data.latest_temperatures_f.keys()):
            self.fill_missing_store_temps()

        self.data.latest_temperatures_f = dict(sorted(self.data.latest_temperatures_f.items()))

    def hp_idu_pwr_w(self) -> Optional[float]:
        """Returns the latest Heat Pump indoor unit power in Watts, or None
        if it does not exist"""
        raw = self.data.latest_channel_values.get(H0CN.hp_idu_pwr)
        if raw is None:
            return None
        return raw

    def hp_odu_pwr_w(self) -> Optional[float]:
        """Returns the latest Heat Pump outdoor unit power in Watts, or None
        if it does not exist"""
        raw = self.data.latest_channel_values.get(H0CN.hp_odu_pwr)
        if raw is None:
            return None
        return raw

    def total_hp_pwr_w(self) -> Optional[float]:
        """Returns the latest Heat Pump total power in Watts, or None
        if it does not exist"""
        idu_pwr = self.hp_idu_pwr_w()
        odu_pwr = self.hp_odu_pwr_w()
        if idu_pwr is None or odu_pwr is None:
            return None
        return idu_pwr + odu_pwr

    @property
    def buffer_temps_available(self):
        return self.data.buffer_temps_available
