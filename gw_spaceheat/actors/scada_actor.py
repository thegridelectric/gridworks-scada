import time
import typing
import uuid
from abc import ABC
from typing import Any, Dict, List, Optional
import pytz
from gwproactor import QOS

from actors.config import ScadaSettings
from actors.scada_data import ScadaData
from data_classes.house_0_layout import House0Layout
from data_classes.house_0_names import H0N, House0RelayIdx
from gw.errors import DcError
from gwproactor import Actor
from gwproto import Message
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import (
    ActorClass,
    ChangeAquastatControl,
    ChangeHeatcallSource,
    ChangeHeatPumpControl,
    ChangePrimaryPumpControl,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    RelayClosedOrOpen
)
from enums import ChangeKeepSend
from named_types import FsmEvent, NewCommandTree
from pydantic import ValidationError

from scada_app_interface import ScadaAppInterface


# from scada_app import ScadaApp


class ScadaActor(Actor, ABC):

    def __init__(self, name: str, services: ScadaAppInterface):
        if not isinstance(services, ScadaAppInterface):
            raise ValueError(
                "ERROR. ScadaActor requires services to be a ScadaAppInterface. "
                f"Received type {type(services)}."
            )
        super().__init__(name, services)
        self.timezone = pytz.timezone(self.settings.timezone_str)

    @property
    def services(self) -> ScadaAppInterface:
        return typing.cast(ScadaAppInterface, self._services)

    @property
    def settings(self) -> ScadaSettings:
        return self.services.settings

    @property
    def node(self) -> ShNode:
        # note: self._node exists in proactor but may be stale
        return self.layout.node(self.name)

    @property
    def layout(self) -> House0Layout:
        return self.services.hardware_layout

    @property
    def data(self) -> ScadaData:
        return self.services.prime_actor.data

    @property
    def atn(self) -> ShNode:
        return self.layout.node(H0N.atn)

    @property
    def primary_scada(self) -> ShNode:
        return self.layout.node(H0N.primary_scada)

    @property
    def atomic_ally(self) -> ShNode:
        return self.layout.node(H0N.atomic_ally)

    @property
    def home_alone(self) -> ShNode:
        return self.layout.node(H0N.home_alone)
    
    @property
    def synth_generator(self) -> ShNode:
        return self.layout.node(H0N.synth_generator)

    def my_actuators(self) -> List[ShNode]:
        """Get all actuator nodes that are descendants of this node in the handle hierarchy"""
        my_handle_prefix = f"{self.node.handle}."
        return [
            node for node in self.layout.actuators
            if node.handle.startswith(my_handle_prefix)
        ]


    ################################
    # Relays
    ################################

    @property
    def vdc_relay(self) -> ShNode:
        return self.layout.node(H0N.vdc_relay)

    @property
    def tstat_common_relay(self) -> ShNode:
        return self.layout.node(H0N.tstat_common_relay)

    @property
    def store_charge_discharge_relay(self) -> ShNode:
        return self.layout.node(H0N.store_charge_discharge_relay)

    @property
    def hp_failsafe_relay(self) -> ShNode:
        return self.layout.node(H0N.hp_failsafe_relay)

    @property
    def hp_scada_ops_relay(self) -> ShNode:
        return self.layout.node(H0N.hp_scada_ops_relay)

    @property
    def thermistor_common_relay(self) -> ShNode:
        return self.layout.node(H0N.thermistor_common_relay)

    @property
    def aquastat_control_relay(self) -> ShNode:
        return self.layout.node(H0N.aquastat_ctrl_relay)

    @property
    def store_pump_failsafe(self) -> ShNode:
        return self.layout.node(H0N.store_pump_failsafe)

    @property
    def primary_pump_scada_ops(self) -> ShNode:
        """relay 11"""
        return self.layout.node(H0N.primary_pump_scada_ops)
    
    @property
    def primary_pump_failsafe(self) -> ShNode:
        """relay 12"""
        return self.layout.node(H0N.primary_pump_failsafe)

    @property
    def hp_loop_on_off(self) -> ShNode:
        """relay 14"""
        return self.layout.node(H0N.hp_loop_on_off)
    
    @property
    def hp_loop_keep_send(self) -> ShNode:
        """relay 15"""
        return self.layout.node(H0N.hp_loop_keep_send)

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
        failsafe_idx = House0RelayIdx.base_stat + 2 * i
        stat_failsafe_name = f"relay{failsafe_idx}"
        return self.layout.node(stat_failsafe_name)

    def stat_ops_relay(self, zone: str) -> ShNode:
        """
        Returns the scada thermostat ops relay for the zone
        Raises a DcError if zone is not in the layout's zone_list
        """
        try:
            i = self.layout.zone_list.index(zone)
        except ValueError as e:
            raise Exception(
                f"Called stat_failsafe_relay for {zone} which does not exist!"
            ) from e
        ops_idx = House0RelayIdx.base_stat + 2 * i + 1
        stat_ops_name = f"relay{ops_idx}"
        return self.layout.node(stat_ops_name)

    ###############################
    # Relay controls
    ################################

    def de_energize(self, relay: ShNode, from_node=None) -> None:
        if relay.ActorClass != ActorClass.Relay:
            self.log(f"Can only energize relays! ignoring energize {relay}")
            return
        if relay == self.hp_scada_ops_relay:
            self.log(f"Can only manage HpScadaOps relay {relay.name} via its boss {self.hp_relay_boss.Name}!")
            return
        zone_by_failsafe_relay: Dict[ShNode, str] = {}
        zone_by_ops_relay: Dict[ShNode, str] = {}
        for zone in self.layout.zone_list:
            zone_by_failsafe_relay[self.stat_failsafe_relay(zone)] = zone
            zone_by_ops_relay[self.stat_ops_relay(zone)] = zone
        if relay in zone_by_failsafe_relay:
            self.heatcall_ctrl_to_stat(zone_by_failsafe_relay[relay], from_node)
        elif relay in zone_by_ops_relay:
            self.stat_ops_open_relay(zone_by_ops_relay[relay], from_node)
        elif relay == self.vdc_relay:
            self.close_vdc_relay(from_node)
        elif relay == self.tstat_common_relay:
            self.close_tstat_common_relay(from_node)
        elif relay == self.store_charge_discharge_relay:
            self.valved_to_discharge_store(from_node)
        elif relay == self.hp_failsafe_relay:
            self.hp_failsafe_switch_to_aquastat(from_node)
        elif relay == self.thermistor_common_relay:
            self.close_thermistor_common_relay(from_node)
        elif relay == self.aquastat_control_relay:
            self.aquastat_ctrl_switch_to_boiler(from_node)
        elif relay == self.store_pump_failsafe:
            self.turn_off_store_pump(from_node)
        elif relay == self.primary_pump_failsafe:
            self.primary_pump_failsafe_to_hp(from_node)
        elif relay == self.primary_pump_scada_ops:
            self.turn_off_primary_pump(from_node)
        elif relay == self.hp_loop_on_off:
            self.sieg_valve_active(from_node)
        elif relay == self.hp_loop_keep_send:
            self.change_to_hp_send_more(from_node)
        else:
            self.log(f"Unrecognized relay {relay}! Not de-energizing")

    def energize(self, relay: ShNode, from_node=None) -> None:
        if relay.ActorClass != ActorClass.Relay:
            self.log(f"Can only energize relays! ignoring energize {relay}")
            return
        if relay == self.hp_scada_ops_relay:
            self.log(f"Can only manage HpScadaOps relay {relay.name} via its boss {self.hp_relay_boss.Name}!")
            return
        zone_by_failsafe_relay: Dict[ShNode, str] = {}
        zone_by_ops_relay: Dict[ShNode, str] = {}
        for zone in self.layout.zone_list:
            zone_by_failsafe_relay[self.stat_failsafe_relay(zone)] = zone
            zone_by_ops_relay[self.stat_ops_relay(zone)] = zone
        if relay in zone_by_failsafe_relay:
            self.heatcall_ctrl_to_scada(zone_by_failsafe_relay[relay], from_node)
        elif zone in zone_by_ops_relay:
            self.stat_ops_close_relay(zone_by_ops_relay[relay], from_node)
        if relay == self.vdc_relay:
            self.open_vdc_relay(from_node)
        elif relay == self.tstat_common_relay:
            self.open_tstat_common_relay(from_node)
        elif relay == self.store_charge_discharge_relay:
            self.valved_to_charge_store(from_node)
        elif relay == self.hp_failsafe_relay:
            self.hp_failsafe_switch_to_scada(from_node)
        elif relay == self.aquastat_control_relay:
            self.aquastat_ctrl_switch_to_scada(from_node)
        elif relay == self.store_pump_failsafe:
            self.turn_on_store_pump(from_node)
        elif relay == self.primary_pump_failsafe:
            self.primary_pump_failsafe_to_scada(from_node)
        elif relay == self.primary_pump_scada_ops:
            self.turn_on_primary_pump(from_node)
        else:
            self.log(f"Unrecognized relay {relay}! Not energizing")

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
                ToHandle=self.vdc_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=trigger_id,
            )
            self._send_to(self.vdc_relay, event, from_node)
            self.log(f"CloseRelay to {self.vdc_relay.name}")
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
                ToHandle=self.vdc_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=trigger_id,
            )
            self._send_to(self.vdc_relay, event, from_node)
            self.log(f"OpenRelay to {self.vdc_relay.name}")
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

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
                ToHandle=self.tstat_common_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.tstat_common_relay, event, from_node)
            self.log(f"{from_node.handle} sending CloseRelay to {self.tstat_common_relay.handle}")
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
                ToHandle=self.tstat_common_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.tstat_common_relay, event, from_node)
            self.log(f"{from_node.handle} sending OpenRelay to {self.tstat_common_relay.handle}")
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
                ToHandle=self.store_charge_discharge_relay.handle,
                EventType=ChangeStoreFlowRelay.enum_name(),
                EventName=ChangeStoreFlowRelay.DischargeStore,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.store_charge_discharge_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending DischargeStore to Store ChargeDischarge {self.store_charge_discharge_relay.handle}"
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
                ToHandle=self.store_charge_discharge_relay.handle,
                EventType=ChangeStoreFlowRelay.enum_name(),
                EventName=ChangeStoreFlowRelay.ChargeStore,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.store_charge_discharge_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending ChargeStore to Store ChargeDischarge {self.store_charge_discharge_relay.handle}"
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
                ToHandle=self.hp_failsafe_relay.handle,
                EventType=ChangeHeatPumpControl.enum_name(),
                EventName=ChangeHeatPumpControl.SwitchToTankAquastat,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_failsafe_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToTankAquastat to Hp Failsafe {self.hp_failsafe_relay.handle}"
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
                ToHandle=self.hp_failsafe_relay.handle,
                EventType=ChangeHeatPumpControl.enum_name(),
                EventName=ChangeHeatPumpControl.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_failsafe_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToScada to Hp Failsafe {self.hp_failsafe_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def turn_on_HP(self, from_node: Optional[ShNode] = None) -> None:
        """ Turn on heat pump

        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.hp_scada_ops_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                # EventType= TurnHpOnOff.enum_name(),
                # EventName=TurnHpOnOff.TurnOn,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_scada_ops_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending CloseRelay to HpScadaOpsRelay {self.hp_scada_ops_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to tell HpScadaOpsRelay to turn on HP but didn't have rights: {e}")

    def turn_off_HP(self, from_node: Optional[ShNode] = None) -> None:
        """  Turn off heat pump by sending trigger to HpRelayBoss
        
        from_node defaults to self.node if no from_node sent.
        Will log an error and do nothing if from_node is not the boss of HpRelayBoss
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.hp_scada_ops_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                # EventType=TurnHpOnOff.enum_name(),
                # EventName=TurnHpOnOff.TurnOff,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_scada_ops_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending OpenRelay to HpScadaOpsRelay {self.hp_scada_ops_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to tell HpScadaOpsRelay to turn off HP but didn't have rights: {e}")

    def close_thermistor_common_relay(self, from_node: Optional[ShNode] = None) -> None:
        """
        Close thermistor common relay (de-energizing relay 2).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.thermistor_common_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.thermistor_common_relay, event, from_node)
            self.log(f"{from_node.handle} sending CloseRelay to {self.thermistor_common_relay.handle}")
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def open_thermistor_common_relay(self, from_node: Optional[ShNode] = None) -> None:
        """
        Open thermistor common relay (energizing relay 2).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.thermistor_common_relay.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.thermistor_common_relay, event, from_node)
            self.log(f"{from_node.handle} sending OpenRelay to {self.thermistor_common_relay.handle}")
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

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
                ToHandle=self.aquastat_control_relay.handle,
                EventType=ChangeAquastatControl.enum_name(),
                EventName=ChangeAquastatControl.SwitchToBoiler,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.aquastat_control_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToBoiler to Boiler Ctrl {self.aquastat_control_relay.handle}"
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
                ToHandle=self.aquastat_control_relay.handle,
                EventType=ChangeAquastatControl.enum_name(),
                EventName=ChangeAquastatControl.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.aquastat_control_relay, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToScada to Aquastat Ctrl {self.aquastat_control_relay.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def turn_off_store_pump(self, from_node: Optional[ShNode] = None) -> None:
        """
        Turn off the store pump by opening (de-energizing) store_pump_failsafe relay (9).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=self.node.handle if from_node is None else from_node.handle,
                ToHandle=self.store_pump_failsafe.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.store_pump_failsafe, event, from_node)
            self.log(
                f"{from_node.handle} sending OpenRelay to StorePump OnOff {self.store_pump_failsafe.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def turn_on_store_pump(self, from_node: Optional[ShNode] = None) -> None:
        """
        Turn on the store pump by closing (energizing) store_pump_failsafe relay (9).
        Will log an error and do nothing if not the boss of this relay
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.store_pump_failsafe.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.store_pump_failsafe, event, from_node)
            self.log(
                f"{self.node.handle if from_node is None else from_node.handle} sending CloseRelay to StorePump OnOff {self.store_pump_failsafe.handle}"
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
                ToHandle=self.primary_pump_failsafe.handle,
                EventType=ChangePrimaryPumpControl.enum_name(),
                EventName=ChangePrimaryPumpControl.SwitchToHeatPump,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.primary_pump_failsafe, event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToHeatPump to {self.primary_pump_failsafe.handle}"
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
                ToHandle=self.primary_pump_failsafe.handle,
                EventType=ChangePrimaryPumpControl.enum_name(),
                EventName=ChangePrimaryPumpControl.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.primary_pump_failsafe, event, from_node)
            self.log(
                f"{self.node.handle if from_node is None else from_node.handle} sending SwitchToHeatPump to {self.primary_pump_failsafe.handle}"
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
                ToHandle=self.primary_pump_scada_ops.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.primary_pump_scada_ops, event, from_node)
            self.log(
                f"{self.node.handle if from_node is None else from_node.handle} sending OpenRelay to {self.primary_pump_scada_ops.handle}"
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
                ToHandle=self.primary_pump_scada_ops.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.primary_pump_scada_ops, event, from_node)
            self.log(
                f"{self.node.handle if from_node is None else from_node.handle} sending CloseRelay to {self.primary_pump_scada_ops.handle}"
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
                ToHandle=self.hp_loop_on_off.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_loop_on_off, event, from_node)
            self.log(
                f"{from_node.handle} sending CloseRelay to HpLoopOnOff relay {self.hp_loop_on_off.handle}"
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
                ToHandle=self.hp_loop_on_off.handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_loop_on_off, event, from_node)
            self.log(
                f"{from_node.handle} sending OpenRelay to HpLoopOnOff relay {self.hp_loop_on_off.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def change_to_hp_send_more(self, from_node: Optional[ShNode] = None) -> None:
        """
        Sets the Keep/Send relay so that if relay 14 is On, the Siegenthaler
        valve moves towards sending MORE water out of the Siegenthaler loop (SendMore)
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.hp_loop_keep_send.handle,
                EventType=ChangeKeepSend.enum_name(),
                EventName=ChangeKeepSend.ChangeToSendMore,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_loop_keep_send, event, from_node)
            self.log(
                f"{from_node.handle} sending SendMore to HpLoopKeepSend relay {self.hp_loop_keep_send.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def change_to_hp_send_less(self, from_node: Optional[ShNode] = None) -> None:
        """
        Sets the Keep/Send relay so that if relay 15 is On, the Siegenthaler
        valve moves towards sending LESS water out of the Siegenthaler loop (SendLess)
        """
        if from_node is None:
            from_node = self.node
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.hp_loop_keep_send.handle,
                EventType=ChangeKeepSend.enum_name(),
                EventName=ChangeKeepSend.ChangeToSendLess,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_loop_keep_send, event, from_node)
            self.log(
                f"{from_node.handle} sending SendLessto HpLoopKeepSend relay {self.hp_loop_keep_send.handle}"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def heatcall_ctrl_to_scada(self, zone: str, from_node: Optional[ShNode] = None) -> None:
        """
        Take over thermostatic control of the zone from the wall thermostat
        by energizing appropriate relay.
        Will log an error and do nothing if not the boss of this relay.
        """
        if from_node is None:
            from_node = self.node
        if zone not in self.layout.zone_list:
            self.log(f"{zone} not a recongized zone!")
            return
        try:
            event = FsmEvent(
                FromHandle=self.node.handle if from_node is None else from_node.handle,
                ToHandle=self.stat_failsafe_relay(zone).handle,
                EventType=ChangeHeatcallSource.enum_name(),
                EventName=ChangeHeatcallSource.SwitchToScada,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )

            self._send_to(self.stat_failsafe_relay(zone), event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToScada to {self.stat_failsafe_relay(zone).handle} (zone {zone})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def heatcall_ctrl_to_stat(self, zone: str, from_node: Optional[ShNode] = None) -> None:
        """
        Return control of the whitewire heatcall signal to the wall thermostat
        by de-energizing appropriate relay.
        Will log an error and do nothing if not the boss of this relay.
        """
        if from_node is None:
            from_node = self.node
        if zone not in self.layout.zone_list:
            self.log(f"{zone} not a recongized zone!")
            return
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.stat_failsafe_relay(zone).handle,
                EventType=ChangeHeatcallSource.enum_name(),
                EventName=ChangeHeatcallSource.SwitchToWallThermostat,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_failsafe_relay(zone), event, from_node)
            self.log(
                f"{from_node.handle} sending SwitchToWallThermostat to {self.stat_failsafe_relay(zone).handle} (zone {zone})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def stat_ops_close_relay(self, zone: str, from_node: Optional[ShNode] = None) -> None:
        """
        Close (energize) the ScadaOps relay for associated zone. Will send a heatcall on the white
        wire IF the associated failsafe relay is energized (switched to SCADA).
        Will log an error and do nothing if not the boss of this relay.
        """
        if from_node is None:
            from_node = self.node
        if zone not in self.layout.zone_list:
            self.log(f"{zone} not a recongized zone!")
            return
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.stat_ops_relay(zone).handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.CloseRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_ops_relay(zone), event, from_node)
            self.log(
                f"{from_node.handle} sending CloseRelay to {self.stat_ops_relay(zone).handle} (zone {zone})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    def stat_ops_open_relay(self, zone: str, from_node: Optional[ShNode] = None) -> None:
        """
        Open (de-energize) the ScadaOps relay for associated zone. Will send 0 on the white
        wire IF the associated failsafe relay is energized (switched to SCADA).
        Will log an error and do nothing if not the boss of this relay.
        """
        if from_node is None:
            from_node = self.node
        if zone not in self.layout.zone_list:
            self.log(f"{zone} not a recongized zone!")
            return
        try:
            event = FsmEvent(
                FromHandle=from_node.handle,
                ToHandle=self.stat_ops_relay(zone).handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.stat_ops_relay(zone), event, from_node)
            self.log(
                f"{from_node.handle} sending OpenRelay to {self.stat_ops_relay(zone).handle} (zone {zone})"
            )
        except ValidationError as e:
            self.log(f"Tried to change a relay but didn't have the rights: {e}")

    @property
    def boss(self) -> ShNode:
        if ".".join(self.node.handle.split(".")[:-1]) == "":
            return self.node

        boss_handle = ".".join(self.node.handle.split(".")[:-1])
        return next(n for n in self.layout.nodes.values() if n.handle == boss_handle)

    def the_boss_of(self, node: ShNode) -> Optional[ShNode]:
        if node.Handle == node.Name:
            return None
        boss_name= node.Handle.split(".")[-2]
        return self.layout.node(boss_name, None)

    def direct_reports(self, boss: Optional[ShNode] = None) -> list[ShNode]:
        if boss is None:
            boss = self.node
        return [n for n in self.layout.nodes.values() if self.the_boss_of(n) == boss]

    def set_command_tree(self, boss_node: ShNode) -> None:
        """ Sets handles for a command tree like this:
           ```
            boss
            ├── relay1 (vdc)
            ├── relay2 (tstat_common)
            └── all other relays and 0-10s
        ```
        Throws exception if boss_node is not in my chain of command
        """
        # TODO: if boss_node is not in my chain of command,
        # raise an error
        my_handle_prefix = f"{self.node.handle}."
        if not boss_node.handle.startswith(my_handle_prefix) and boss_node != self.node:
            raise Exception(f"{self.node.handle} cannot set command tree for boss_node {boss_node.handle}!")

        for node in self.my_actuators():
            node.Handle =  f"{boss_node.handle}.{node.Name}"
        self._send_to(
            self.atn,
            NewCommandTree(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                ShNodes=list(self.layout.nodes.values()),
                UnixMs=int(time.time() * 1000),
            ),
        )
        self.log(f"Set {boss_node.handle} command tree")

    def _send_to(self, dst: ShNode, payload: Any, src: Optional[ShNode] = None) -> None:
        if dst is None:
            return
        if src is None:
            src = self.node
        # HACK FOR nodes whose 'actors' are handled by their parent's communicator
        communicator_by_name = {dst.Name: dst.Name}
        communicator_by_name[H0N.home_alone_normal] = H0N.home_alone
        
        message = Message(Src=src.name, Dst=communicator_by_name[dst.Name], Payload=payload)

        if communicator_by_name[dst.name] in set(self.services.get_communicator_names()) | {
            self.name
        }:  # noqa: SLF001
            self.services.send(message)
        elif dst.Name == H0N.admin:
            self.services.publish_message(
                link_name=self.services.ADMIN_MQTT,
                message=Message(
                    Src=self.services.publication_name, Dst=dst.Name, Payload=payload
                ),
                qos=QOS.AtMostOnce,
            ) # noqa: SLF001
        elif dst.Name == H0N.atn:
            self.services.publish_upstream(payload)  # noqa: SLF001
        else:
            self.services.publish_message(
                self.services.LOCAL_MQTT, message
            )  # noqa: SLF001

    def log(self, note: str) -> None:
        log_str = f"[{self.name}] {note}"
        self.services.logger.error(log_str)

    ##########################################
    # Data related
    ##########################################

    def hp_relay_closed(self) -> bool:
        if self.hp_scada_ops_relay.Name not in self.data.latest_machine_state:
            raise Exception("We should know the state of the hp ops relay!")
        if self.data.latest_machine_state[self.hp_scada_ops_relay.Name].State == RelayClosedOrOpen.RelayClosed:
            return True
        return False
