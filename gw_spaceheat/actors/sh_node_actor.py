import time
import typing
import uuid
from abc import ABC
from typing import cast, Any, List, Optional
import pytz

from pydantic import ValidationError

from gwproactor import QOS
from gw.errors import DcError
from gwproactor import Actor
from gwproto import Message

from actors.config import ScadaSettings
from actors.scada_data import ScadaData
from gwsproto.conversions.temperature import convert_temp_to_f
from gwsproto.data_classes.house_0_layout import House0Layout
from gwsproto.data_classes.house_0_names import H0N, H0CN, House0RelayIdx

from gwsproto.data_classes.sh_node import ShNode

from gwsproto.enums import (
    ActorClass,
    ChangeAquastatControl,
    ChangeHeatcallSource,
    ChangeHeatPumpControl,
    ChangeKeepSend,
    ChangePrimaryPumpControl,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    LogLevel,
    RelayClosedOrOpen,
    StoreFlowRelay,
    TelemetryName,
    TurnHpOnOff
)

from gwsproto.data_classes.components.i2c_multichannel_dt_relay_component import (
    I2cMultichannelDtRelayComponent,
)
from gwsproto.named_types import FsmEvent, Glitch, HeatingForecast, NewCommandTree

from scada_app_interface import ScadaAppInterface



class ShNodeActor(Actor, ABC):
    MIN_USED_TANK_TEMP_F = 70
    MAX_VALID_TANK_TEMP_F = 200
    NUM_LAYERS_PER_TANK = 3
    SIMULATED_TANK_TEMP_F = 70
    PUMP_FLOW_GPM_THRESHOLD = 0.1

    def __init__(self, name: str, services: ScadaAppInterface):
        if not isinstance(services, ScadaAppInterface):
            raise ValueError(
                "ERROR. ShNodeActor requires services to be a ScadaAppInterface. "
                f"Received type {type(services)}."
            )
        super().__init__(name, services)
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.h0n = self.layout.h0n
        self.h0cn = self.layout.h0cn

        # set temperature_channel_names
        self.tank_temp_channel_names = list(self.h0cn.buffer.effective)
        for tank_idx in sorted(self.h0cn.tank):
            tank = self.h0cn.tank[tank_idx]
            self.tank_temp_channel_names.extend([tank.depth1, tank.depth2, tank.depth3])

        self.pipe_temp_channel_names = [
            self.h0cn.hp_ewt, self.h0cn.hp_lwt,
             self.h0cn.dist_swt, self.h0cn.dist_rwt, 
            self.h0cn.buffer_cold_pipe, self.h0cn.buffer_hot_pipe, 
            self.h0cn.store_cold_pipe, self.h0cn.store_hot_pipe,
        ]

        self.temperature_channel_names =  self.tank_temp_channel_names + self.pipe_temp_channel_names

    @property
    def services(self) -> ScadaAppInterface:
        return typing.cast(ScadaAppInterface, self._services)

    @property
    def settings(self) -> ScadaSettings:
        return self.services.settings

    @property
    def node(self) -> ShNode:
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
    def derived_generator(self) -> ShNode:
        return self.layout.node(H0N.derived_generator)

    @property
    def hp_boss(self) -> ShNode:
        if not self.layout.use_sieg_loop:
            raise Exception("Should not be calling for hp_boss if not using sieg loop")
        return self.layout.node(H0N.hp_boss)

    @property
    def sieg_loop(self) -> ShNode:
        if not self.layout.use_sieg_loop:
            raise Exception("Should not be calling for sieg_loop if not using sieg loop")
        return self.layout.node(H0N.sieg_loop)

    @property
    def pico_cycler(self) -> ShNode:
        return self.layout.nodes[H0N.pico_cycler]

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

    def discharging_store(self) -> bool:
        """
        Returns True if the system is actively discharging the store:
        - the charge/discharge relay is set to DischargingStore
        - and the store pump is moving water above threshold
        """
        relay_state = self.data.latest_machine_state.get(
            self.store_charge_discharge_relay.name
        )

        if relay_state != StoreFlowRelay.DischargingStore:
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
        relay_state = self.data.latest_machine_state.get(
            self.store_charge_discharge_relay.name
        )
        if relay_state != StoreFlowRelay.DischargingStore:
            return False

        primary_flow = self.data.latest_channel_values.get(H0CN.primary_flow) or 0
        return primary_flow > self.PUMP_FLOW_GPM_THRESHOLD * 100

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

    def de_energize(self, relay: ShNode, from_node: Optional[ShNode] = None):
        if relay.ActorClass != ActorClass.Relay:
            self.log(f"Can only de-energize relays! ignoring energize {relay}")
            return
        component = cast(I2cMultichannelDtRelayComponent, relay.component)
        relay_config = next(
            (x for x in component.gt.ConfigList if x.ActorName == relay.name),
            None,
        )
        if relay_config is None:
            self.log(f"Unrecognized relay {relay.name}. Not de-energizing")
            return
        try:
            event = FsmEvent(
                FromHandle=self.node.handle if from_node is None else from_node.handle,
                ToHandle=relay.handle,
                EventType=relay_config.EventType,
                EventName=relay_config.DeEnergizingEvent,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(relay, event, from_node)
            self.log(f"{relay_config.DeEnergizingEvent} to {relay.name} (de-energizing)")
        except ValidationError as e:
            self.log(f"Tried to de-energize {relay.name} but didn't have the rights: {e}")

    def energize(self, relay: ShNode, from_node: Optional[ShNode] = None):
        if relay.ActorClass != ActorClass.Relay:
            self.log(f"Can only de-energize relays! ignoring energize {relay}")
            return
        component = cast(I2cMultichannelDtRelayComponent, relay.component)
        relay_config = next(
            (x for x in component.gt.ConfigList if x.ActorName == relay.name),
            None,
        )
        if relay_config is None:
            self.log(f"Unrecognized relay {relay.name}. Not de-energizing")
            return
        try:
            event = FsmEvent(
                FromHandle=self.node.handle if from_node is None else from_node.handle,
                ToHandle=relay.handle,
                EventType=relay_config.EventType,
                EventName=relay_config.EnergizingEvent,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(relay, event, from_node)
            self.log(f"{relay_config.EnergizingEvent} to {relay.name} (energizing)")
        except ValidationError as e:
            self.log(f"Tried to energize {relay.name} but didn't have the rights: {e}")


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

        if self.layout.use_sieg_loop:
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
                    ToHandle=self.hp_scada_ops_relay.handle,
                    EventType=ChangeRelayState.enum_name(),
                    EventName=ChangeRelayState.CloseRelay,
                    SendTimeUnixMs=int(time.time() * 1000),
                    TriggerId=str(uuid.uuid4()),
                )
                self._send_to(self.hp_scada_ops_relay, event, from_node)
                self.log(f"{from_node.handle} sending CloseRelay to HpScadaOpsRelay {self.hp_scada_ops_relay.handle}")
            except ValidationError as e:
                self.log(f"Tried to tell HpScadaOpsRelay to turn on HP but didn't have rights: {e}")


    def turn_off_HP(self, from_node: Optional[ShNode] = None) -> None:
        """  Turn off heat pump by sending trigger to HpRelayBoss
        
        from_node defaults to self.node if no from_node sent.
        Will log an error and do nothing if from_node is not the boss of HpRelayBoss
        """
        if from_node is None:
            from_node = self.node

        if self.layout.use_sieg_loop:
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
                    ToHandle=self.hp_scada_ops_relay.handle,
                    EventType=ChangeRelayState.enum_name(),
                    EventName=ChangeRelayState.OpenRelay,
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
                ToHandle=self.hp_loop_keep_send.handle,
                EventType=ChangeKeepSend.enum_name(),
                EventName=ChangeKeepSend.ChangeToKeepLess,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(self.hp_loop_keep_send, event, from_node)
            self.log(
                f"{from_node.handle} sending SendMore to HpLoopKeepSend relay {self.hp_loop_keep_send.handle}"
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
                ToHandle=self.hp_loop_keep_send.handle,
                EventType=ChangeKeepSend.enum_name(),
                EventName=ChangeKeepSend.ChangeToKeepMore,
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
        if node.Handle is None:
            return None
        boss_name= node.Handle.split(".")[-2]
        return self.layout.node(boss_name, None)

    def direct_reports(self, boss: Optional[ShNode] = None) -> list[ShNode]:
        if boss is None:
            boss = self.node
        return [n for n in self.layout.nodes.values() if self.the_boss_of(n) == boss]

    def set_hierarchical_fsm_handles(self, boss_node: ShNode) -> None:
        """
        ```
        boss
        ├────────────────────── hp-boss
        └─────sieg-loop         └── relay6 (hp_scada_ops_relay)
                ├─ relay14 (hp_loop_on_off)
                └─ relay15 (hp_loop_keep_send)
        ```
        """
        if not self.layout.use_sieg_loop:
            raise Exception("don't call this unless layout uses sieg loop")
        self.log(f"Setting fsm handles under {boss_node.name}")
        hp_boss = self.layout.node(H0N.hp_boss)
        hp_boss.Handle = f"{boss_node.handle}.{hp_boss.Name}"

        scada_ops_relay = self.layout.node(H0N.hp_scada_ops_relay)
        scada_ops_relay.Handle = f"{hp_boss.Handle}.{scada_ops_relay.Name}"

        sieg_loop = self.layout.node(H0N.sieg_loop)
        sieg_loop.Handle = f"{boss_node.handle}.{sieg_loop.Name}"

        sieg_keep_send =  self.layout.node(H0N.hp_loop_keep_send)
        sieg_keep_send.Handle = f"{sieg_loop.Handle}.{sieg_keep_send.Name}"

        sieg_on_off = self.layout.node(H0N.hp_loop_on_off)
        sieg_on_off.Handle = f"{sieg_loop.Handle}.{sieg_on_off.Name}"

    def set_command_tree(self, boss_node: ShNode) -> None:
        """
        If FlowManifoldVariant is House0Sieg:
           ```
            boss
            ├─────────────────────────────────────────── hp-boss
            ├───────────────────────────sieg-loop           └── relay6 (hp_scada_ops_relay)
            ├                             ├─ relay14 (hp_loop_on_off)
            ├── relay1 (vdc)              └─ relay15 (hp_loop_keep_send)
            ├── relay2 (tstat_common)
            └── all other relays and 0-10s
        ```
        If FlowManifoldVariant is House0, all actuators report directly to boss
        Throws exception if boss_node is not in my chain of command
        """

        my_handle_prefix = f"{self.node.handle}."
        if not boss_node.handle.startswith(my_handle_prefix) and boss_node != self.node:
            raise Exception(f"{self.node.handle} cannot set command tree for boss_node {boss_node.handle}!")

        if self.layout.use_sieg_loop:
            self.set_hierarchical_fsm_handles(boss_node)
            for node in self.my_actuators():
                if node.Name not in [H0N.hp_scada_ops_relay, H0N.hp_loop_keep_send, H0N.hp_loop_on_off]:
                    node.Handle =  f"{boss_node.handle}.{node.Name}"
        else:
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
                link_name=self.services.prime_actor.ADMIN_MQTT,
                message=Message(
                    Src=self.services.publication_name, Dst=dst.Name, Payload=payload
                ),
                qos=QOS.AtMostOnce,
            ) # noqa: SLF001
        elif dst.Name == H0N.atn:
            self.services.publish_upstream(payload)  # noqa: SLF001
        else:
            self.services.publish_message(
                self.services.prime_actor.LOCAL_MQTT, message
            )  # noqa: SLF001

    def log(self, note: str) -> None:
        log_str = f"[{self.name}] {note}"
        self.services.logger.error(log_str)

    ##########################################
    # Data related
    ##########################################

    @property
    def heating_forecast(self) -> HeatingForecast | None:
        return self.data.heating_forecast

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

    #-----------------------------------------------------------------------
    # Temperature related
    #-----------------------------------------------------------------------

    @property
    def latest_temps_f(self) -> dict[str, float]:
        return self.data.latest_temperatures_f

    @property
    def buffer_temps_available(self):
        return self.data.buffer_temps_available

    def is_buffer_empty(self) -> bool:
        """
        Returns True if the buffer does not contain enough usable heat
        to meet the near-term required return-water temperature.

        Uses the coldest available top-of-buffer measurement and the
        maximum required RWT minus delta-T over the next few hours.

        If forecasts are unavailable, returns False (cannot assert empty).
        """

        # Select the best available "top of buffer" temperature channel
        if H0CN.buffer.depth1 in self.latest_temps_f:
            buffer_top_ch = H0CN.buffer.depth1
        elif H0CN.dist_swt in self.latest_temps_f:
            buffer_top_ch = H0CN.dist_swt
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

        min_buffer_temp_f = round(max_rswt - max_delta_t, 1)
        min_buffer_temp_f = min(min_buffer_temp_f, self.data.ha1_params.MaxEwtF-10)
        buffer_temp_f = self.latest_temps_f[buffer_top_ch]

        if buffer_temp_f < min_buffer_temp_f:
            self.log(
                f"Buffer empty ({buffer_top_ch}: {buffer_temp_f} < {min_buffer_temp_f} F)"
            )
            return True
        else:
            self.log(
                f"Buffer not empty ({buffer_top_ch}: {buffer_temp_f} >= {min_buffer_temp_f} F)"
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
        else:
            max_buffer = round(max(self.heating_forecast.RswtF[:3]), 1)
            max_buffer = min(max_buffer, self.data.ha1_params.MaxEwtF)

        buffer_full_ch_temp = self.latest_temps_f[buffer_full_ch]
        if buffer_full_ch_temp > max_buffer:
            self.log(
                f"Buffer full ({buffer_full_ch}: {buffer_full_ch_temp} > {max_buffer} F)"
            )
            return True
        else:
            self.log(
                f"Buffer not full ({buffer_full_ch}: {buffer_full_ch_temp} <= {max_buffer} F)"
            )
            return False

    def is_buffer_full_alt(self) -> bool:
        """
        Reorganization of the default to hp_ewt IF there is water flowing from the hp to the house,
        otherwise tank 3
        """
        if (
            self.flowing_from_hp_to_house()
            and H0CN.hp_ewt in self.latest_temps_f
        ):
            buffer_full_ch = H0CN.hp_ewt

        elif H0CN.buffer.depth3 in self.latest_temps_f:
            buffer_full_ch = H0CN.buffer.depth3

        elif H0CN.buffer_cold_pipe in self.latest_temps_f:
            buffer_full_ch = H0CN.buffer_cold_pipe
        
        elif ( 
            self.discharging_store()
            and H0CN.store_cold_pipe in self.latest_temps_f
        ):
            buffer_full_ch = H0CN.store_cold_pipe

        else:
            return False

        if self.heating_forecast is None:
            max_buffer = self.data.ha1_params.MaxEwtF
        else:
            max_buffer = round(max(self.heating_forecast.RswtF[:3]), 1)
            max_buffer = min(max_buffer, self.data.ha1_params.MaxEwtF)

        buffer_full_ch_temp = self.latest_temps_f[buffer_full_ch]
        if buffer_full_ch_temp > max_buffer:
            self.log(
                f"Buffer full ({buffer_full_ch}: {buffer_full_ch_temp} > {max_buffer} F)"
            )
            return True
        else:
            self.log(
                f"Buffer not full ({buffer_full_ch}: {buffer_full_ch_temp} <= {max_buffer} F)"
            )
            return False

    def is_buffer_charge_limited(self) -> bool:
        """
        Returns True if the buffer cannot accept more heat without exceeding MaxEwtF.
        This is a physical limit.
        """
        if H0CN.buffer_cold_pipe not in self.latest_temps_f:
            return False

        return self.latest_temps_f[H0CN.buffer_cold_pipe] >= self.data.ha1_params.MaxEwtF

    def is_storage_colder_than_buffer(self, min_delta_f: float = 5.4) -> bool:
        """
        Returns True if the top of the storage is at least `min_delta_f` colder
        than the top of the buffer.

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
        else:
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

        return self.latest_temps_f[buffer_top] > (
            self.latest_temps_f[tank_top] + min_delta_f
        )

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

        if not self.settings.is_simulated:
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
        else:
            self.log("IN SIMULATION - set all temperatures to 70 degF")
            self.data.latest_temperatures_f = {
                ch: self.SIMULATED_TANK_TEMP_F for ch in self.temperature_channel_names
            }

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

    def lwt_f(self) -> Optional[float]:
        """Returns the latest Heat pump leaving water temp in deg F, or None
        if it does not exist"""
        raw = self.data.latest_channel_values.get(H0CN.hp_lwt)
        if raw is None:
            return None
        unit = self.layout.channel_registry.unit(H0CN.hp_lwt)
        if unit is None:
            raise Exception("hp_lwt must belong!")
        return convert_temp_to_f(
                        raw=raw,
                        encoding=unit
                    )

    def ewt_f(self) -> Optional[float]:
        """Returns the latest Heat pump entering water temp in deg F, or None
        if it does not exist"""
        raw = self.data.latest_channel_values.get(H0CN.hp_ewt)
        if raw is None:
            return None
        unit = self.layout.channel_registry.unit(H0CN.hp_ewt)
        if unit is None:
            raise Exception("hp_ewt must belong!")
        return convert_temp_to_f(
                        raw=raw,
                        encoding=unit
                    )

    def sieg_cold_f(self) -> Optional[float]:
        """Returns the latest Siegenthaler Cold temp in deg F, or None
        if it does not exist"""
        raw = self.data.latest_channel_values.get(H0CN.sieg_cold)
        if raw is None:
            return None
        unit = self.layout.channel_registry.unit(H0CN.sieg_cold)
        if unit is None:
            raise Exception("sieg_cold must belong!")
        return convert_temp_to_f(
                        raw=raw,
                        encoding=unit
                    )

    def sieg_flow_gpm(self) -> Optional[float]:
        """Returns the latest siegenthaler flow in gallons per minute, or None
        if it does not exist"""
        sieg_x_100 = self.data.latest_channel_values.get(H0CN.sieg_flow)
        if sieg_x_100 is None:
            return None
        return sieg_x_100 / 100

    def primary_flow_gpm(self) -> Optional[float]:
        """Returns the latest primary flow in gallons per minute, or None
        if it does not exist"""
        primary_x_100 = self.data.latest_channel_values.get(H0CN.primary_flow)
        if primary_x_100 is None:
            return None
        return primary_x_100 / 100

    def lift_f(self) -> Optional[float]:
        """ The lift of the heat pump: leaving water temp minus entering water temp.
        Returns 0 if this is negative (e.g. during defrost). Returns None if missing
        a key temp.
        """
        lwt_f = self.lwt_f(); ewt_f = self.ewt_f()
        if lwt_f is None or ewt_f is None:
            return None
        return max(0, lwt_f - ewt_f)

    def hottest_store_temp_f(self) -> float | None:
        raw = self.data.latest_channel_values.get(self.h0cn.tank[1].depth1)
        if raw is None:
            return None
        unit = self.layout.channel_registry.unit(self.h0cn.tank[1].depth1)
        if unit is None:
            raise Exception("tank1-depth1 must belong!")
        return convert_temp_to_f(
                        raw=raw,
                        encoding=unit
                    )

    def coldest_store_temp_f(self) -> float | None:
        last_tank_idx = max(self.h0cn.tank)
        raw = self.data.latest_channel_values.get(self.h0cn.tank[last_tank_idx].depth3)
        if raw is None:
            return None
        unit = self.layout.channel_registry.unit(self.h0cn.tank[last_tank_idx].depth3)
        if unit is None:
            raise Exception("tank1-depth1 must belong!")
        return convert_temp_to_f(
                        raw=raw,
                        encoding=unit
                    )

    def hottest_buffer_temp_f(self) -> float | None:
        raw = self.data.latest_channel_values.get(H0CN.buffer.depth1)
        if raw is None:
            return None
        unit = self.layout.channel_registry.unit(H0CN.buffer.depth1)
        if unit is None:
            raise Exception("buffer-depth1 must belong!")
        return convert_temp_to_f(
                        raw=raw,
                        encoding=unit
                    )

    def coldest_buffer_temp_f(self) -> float | None:
        raw = self.data.latest_channel_values.get(H0CN.buffer.depth3)
        if raw is None:
            return None
        unit = self.layout.channel_registry.unit(H0CN.buffer.depth3)
        if unit is None:
            raise Exception("buffer-depth3 must belong!")
        return convert_temp_to_f(
                        raw=raw,
                        encoding=unit
                    )

    def charge_discharge_relay_state(self) -> StoreFlowRelay:
        """ Returns DischargingStore if relay 3 is de-energized (ISO Valve opened, charge/discharge
        valve in discharge position.) Returns Charging store if energized (ISO Valve closed, charge/discharge
        valve in charge position) """
        sms = self.data.latest_machine_state.get(H0N.store_charge_discharge_relay)
        if sms is None:
            raise Exception("That's strange! Should have a relay state for the charge discharge relay!")
        if sms.StateEnum != StoreFlowRelay.enum_name():
            raise Exception(f"That's strange. Expected StateEnum 'store.flow.relay' but got {sms.StateEnum}")
        return StoreFlowRelay(sms.State)

    def hp_relay_state(self) -> RelayClosedOrOpen:
        sms = self.data.latest_machine_state[H0N.hp_scada_ops_relay]
        if sms is None:
            raise Exception("That's strange! Should have a rela state for the Hp Scada Ops relay!")
        if sms.StateEnum != RelayClosedOrOpen.enum_name():
            raise Exception(f"That's strange. Expected StateEnum 'relay.closed.or.open' but got {sms.StateEnum}")
        return RelayClosedOrOpen(sms.State)

    def alert(self, summary: str, details: str, log_level=LogLevel.Critical) -> None:
        """Send Critical Glitch """
        self._send_to(self.atn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.node.Name,
                Type=log_level,
                Summary=summary,
                Details=details
            )
        )
        self.log(f"Critical Glitch: {summary}")

    def send_warning(self, summary: str, details: str = "") -> None:
        """Send Warning Glitch"""
        self._send_to(self.atn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.node.Name,
                Type=LogLevel.Warning,
                Summary=summary,
                Details=details
            )
        )
        self.log(f"Warning Glitch: {summary}")

    def send_error(self, summary: str, details: str = "") -> None:
        """Send Error Glitch"""
        self._send_to(self.atn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.node.Name,
                Type=LogLevel.Error,
                Summary=summary,
                Details=details
            )
        )
        self.log(f"Error Glitch: {summary}")

    def send_info(self, summary: str, details: str = "") -> None:
        """Send Info Glitch"""
        self._send_to(self.atn,
            Glitch(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                Node=self.node.Name,
                Type=LogLevel.Info,
                Summary=summary,
                Details=details
            )
        )
        self.log(f"Info Glitch: {summary}")