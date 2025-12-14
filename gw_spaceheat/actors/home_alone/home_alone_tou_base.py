import asyncio
from abc import abstractmethod
from typing import Dict, List, Optional, Sequence, cast
from enum import auto
import time
import uuid
from datetime import datetime, timedelta
from gw.enums import GwStrEnum
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import ActorClass
from gwproto.named_types import AnalogDispatch
from result import Ok, Result
from transitions import Machine
from gwsproto.data_classes.house_0_names import H0N, H0CN
from gwproto.data_classes.components.dfr_component import DfrComponent
from gwsproto.enums import HomeAloneStrategy
from actors.scada_actor import ScadaActor
from gwsproto.named_types import (ActuatorsReady,
            GoDormant, Glitch, Ha1Params, HeatingForecast,
            NewCommandTree, SingleMachineState, WakeUp)
from gwsproto.enums import HomeAloneStrategy, LocalControlTopState, LogLevel
from gwsproto.enums import LocalControlTopStateEvent
from scada_app_interface import ScadaAppInterface


class HomeAloneTouBase(ScadaActor):
    """Manages the top level state machine for home alone in a time of use framework. Every home 
    alone node has a strategy. That strategy is in charge of how the "normal" home alone code works. Strategy-specific code
    should inherit from this base class."""
    MAIN_LOOP_SLEEP_SECONDS = 60
    BLIND_MINUTES = 5

    top_states = LocalControlTopState.values()
    top_transitions = [
        {"trigger": "TopGoDormant", "source": "Normal", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "UsingNonElectricBackup", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "ScadaBlind", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "Monitor", "dest": "Dormant"},
        {"trigger": "TopWakeUp", "source": "Dormant", "dest": "Normal"},
        {"trigger": "SystemCold", "source": "Normal", "dest": "UsingNonElectricBackup"},
        {"trigger": "CriticalZonesAtSetpointOffpeak", "source": "UsingNonElectricBackup", "dest": "Normal"},
        {"trigger": "MissingData", "source": "Normal", "dest": "ScadaBlind"},
        {"trigger": "DataAvailable", "source": "ScadaBlind", "dest": "Normal"},
        {"trigger": "MonitorOnly", "source": "Normal", "dest": "Monitor"},
        {"trigger": "MonitorOnly", "source": "Dormant", "dest": "Monitor"},
        {"trigger": "MonitorAndControl", "source": "Monitor", "dest": "Normal"}
    ]

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.cn: H0CN = self.layout.channel_names
        self.strategy = HomeAloneStrategy(getattr(self.node, "Strategy", None))
        self._stop_requested: bool = False
        self.hardware_layout = self._services.hardware_layout
        
        self.time_since_blind: Optional[float] = None
        self.scadablind_scada = False
        self.scadablind_boiler = False
        self.strategy = HomeAloneStrategy(getattr(self.node, "Strategy", None))
        if self.strategy is None:
            raise Exception("Expect to have a HomeAlone strategy!!")
        self.top_machine = Machine(
            model=self,
            states=HomeAloneTouBase.top_states,
            transitions=HomeAloneTouBase.top_transitions,
            initial=LocalControlTopState.Normal,
            send_event=False,
            model_attribute="top_state",
        )  
        if self.settings.monitor_only:
            self.top_state = LocalControlTopState.Monitor
        else: 
            self.top_state = LocalControlTopState.Normal
        self.is_simulated = self.settings.is_simulated
        self.oil_boiler_during_onpeak = self.settings.oil_boiler_backup
        self.log(f"Params: {self.params}")
        self.log(f"self.is_simulated: {self.is_simulated}")
        self.heating_forecast: Optional[HeatingForecast] = None
        self.zone_setpoints = {}
        if H0N.home_alone_normal not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_normal} node!!")
        if H0N.home_alone_scada_blind not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_scada_blind} node!!")
        if H0N.home_alone_backup not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_backup} node!!")
        self.set_command_tree(boss_node=self.normal_node)
        self.latest_temperatures: Dict[str, int] = {} # 
        self.actuators_initialized = False
        self.actuators_ready = False
        self.pump_doctor_running = False
        self.pump_doctor_attempts = 0
        self.time_dist_pump_should_be_on = None

    @property
    def normal_node(self) -> ShNode:
        """
        Overwrite the standard 
        """
        return self.layout.node(H0N.home_alone_normal)

    @property
    def backup_node(self) -> ShNode:
        """ 
        The node / state machine responsible
        for backup operations
        """
        return self.layout.node(H0N.home_alone_backup)

    @property
    def scada_blind_node(self) -> ShNode:
        """
        THe node / state machine responsible
        for when the scada has missing data (forecasts / temperatures)
        """
        return self.layout.node(H0N.home_alone_scada_blind)

    @property
    def params(self) -> Ha1Params:
        return self.data.ha1_params

    def set_limited_command_tree(self, boss: ShNode) -> None:
        """
        ```
        h                               
        └─ BOSS                                                  
            ├── relay1 (vdc)                 
            ├── relay2 (tstat_common)
            └── all other relays and 0-10s
        ```
        """
        if boss is None:
            raise ValueError(f"Cannot set limited command tree: boss node is None")
        
        for node in self.my_actuators():
            node.Handle = f"{boss.Handle}.{node.Name}"
        self._send_to(
            self.atn,
            NewCommandTree(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                ShNodes=list(self.layout.nodes.values()),
                UnixMs=int(time.time() * 1000),
            ),
        )
        self.log(f"Set ha command tree w all actuators reporting to {boss.handle}")

    def trigger_top_event(self, cause: LocalControlTopStateEvent) -> None:
        """
        Trigger top event. Set relays_initialized to False if top state
        is Dormant. Report state change.
        """
        orig_state = self.top_state
        now_ms = int(time.time() * 1000)
        if cause == LocalControlTopStateEvent.SystemCold:
            self.SystemCold()
        elif cause == LocalControlTopStateEvent.TopGoDormant:
            self.TopGoDormant()
        elif cause == LocalControlTopStateEvent.TopWakeUp:
            self.TopWakeUp()
        elif cause == LocalControlTopStateEvent.MissingData:
            self.MissingData()
        elif cause == LocalControlTopStateEvent.DataAvailable:
            self.DataAvailable()
        elif cause == LocalControlTopStateEvent.MonitorOnly:
            self.MonitorOnly()
        elif cause == LocalControlTopStateEvent.MonitorAndControl:
            self.MonitorAndControl()
        elif cause == LocalControlTopStateEvent.CriticalZonesAtSetpointOffpeak:
            self.CriticalZonesAtSetpointOffpeak()
        else:
            raise Exception(f"Unknown top event {cause}")
        
        self.log(f"Top State {cause.value}: {orig_state} -> {self.top_state}")
        if self.top_state == LocalControlTopState.Normal:
            self.actuators_initialized = False
            self.log(f"need to initialize actuators again")

        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=LocalControlTopState.enum_name(),
                State=self.top_state,
                UnixMs=now_ms,
                Cause=cause.value,
            ),
        )
        self.log("Set top state command tree")

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]

    async def pump_doctor(self):
        # NOTE:
        # pump_doctor runs inline inside the HomeAlone main loop.
        # Any waits here MUST pat the internal watchdog or SCADA will reboot.
        self.pump_doctor_running = True
        try:
            self.log("[Pump doctor] Starting...")
            # self.alert('Pump doctor starting for the dist pump at Elm, please monitor', 'Pump doctor starting')

            if self.pump_doctor_attempts >= 3:
                self.log("[Pump doctor] Max attempts reached, giving up")
                return
            if not self.layout.zone_list:
                self.log("[Pump doctor] Could not find a zone list")
                return

            # Switch all zones to Scada
            self.log("[Pump doctor] Switching zone relays to Scada")
            for zone in self.layout.zone_list:
                self.heatcall_ctrl_to_scada(zone=zone, from_node=self.normal_node)            
            
            # Set DFR to 0
            self.log("[Pump doctor] Waiting 10 seconds")
            await self.await_with_watchdog(10)
            self.log("[Pump doctor] Setting dist DFR to 0")
            self.services.send_threadsafe(
                Message(
                    Src=self.name,
                    Dst=self.primary_scada.name,
                    Payload=AnalogDispatch(
                        FromGNodeAlias=self.layout.atn_g_node_alias,
                        FromHandle="auto",
                        ToHandle="auto.dist-010v",
                        AboutName="dist-010v",
                        Value=0,
                        TriggerId=str(uuid.uuid4()),
                        UnixTimeMs=int(time.time() * 1000),
                    ),
                )
            )

            # Switch all zones to Closed
            self.log("[Pump doctor] Waiting 5 seconds")
            await self.await_with_watchdog(5)
            self.log("[Pump doctor] Switching zone relays to Closed")
            for zone in self.layout.zone_list:
                self.stat_ops_close_relay(zone=zone, from_node=self.normal_node)

            # Wait to see flow come in
            self.log("[Pump doctor] Waiting 1 minute")
            await self.await_with_watchdog(int(1*60))

            # Check if dist flow is detected, if yes switch all zones back Open and Thermostat
            if H0CN.dist_flow not in self.data.latest_channel_values or self.data.latest_channel_values[H0CN.dist_flow] is None:
                self.log("[Pump doctor] Dist flow not found in latest channel values")
                return
            if self.data.latest_channel_values[H0CN.dist_flow]/100 > 0.5:
                self.log('[Pump doctor] Dist flow detected - success!')
                self.pump_doctor_attempts = 0
                self.log("[Pump doctor] Switching zones back to Open and Thermostat")                
            else:
                self.log('[Pump doctor] No dist flow detected - did not work')
                self.pump_doctor_attempts += 1
        except Exception as e:
            self.log(f"[Pump doctor] Error: {e}")
        finally:
            self.pump_doctor_running = False
            self.log("[Pump doctor] Setting 0-10V back to default level")
            self.set_010_defaults()
            self.log("[Pump doctor] Switching zones back to thermostat")
            for zone in self.layout.zone_list:
                self.heatcall_ctrl_to_stat(zone=zone, from_node=self.normal_node)
            await self.await_with_watchdog(5)
            self.log("[Pump doctor] Switching scada thermostat relays back to open")
            for zone in self.layout.zone_list:
                self.stat_ops_open_relay(zone=zone, from_node=self.normal_node)
        
    async def check_dist_pump(self):
        if self.pump_doctor_running:
            self.log("Pump doctor already running, skipping dist pump check")
            return
        self.log("Checking dist pump activity...")
        dist_pump_should_be_off = True
        for i in H0CN.zone:
            zone_whitewire_name = H0CN.zone[i].whitewire_pwr
            if zone_whitewire_name not in self.data.latest_channel_values or self.data.latest_channel_values[zone_whitewire_name] is None:
                self.log(f"{zone_whitewire_name} was not found in latest channel values")
                if 'zone4-master-whitewire' in zone_whitewire_name:
                    for existing_zone_whitewire_name in self.data.latest_channel_values:
                        if (
                            'whitewire' in existing_zone_whitewire_name and 
                            f"{zone_whitewire_name.split('-')[0]}-{zone_whitewire_name.split('-')[1]}" in existing_zone_whitewire_name
                        ):
                            self.log(f"Found {existing_zone_whitewire_name} in latest channel values")
                            zone_whitewire_name = existing_zone_whitewire_name
                            break
                continue
            if abs(self.data.latest_channel_values[zone_whitewire_name]) > self.settings.whitewire_threshold_watts:
                self.log(f"{zone_whitewire_name} is above threshold ({self.data.latest_channel_values[zone_whitewire_name]} > {self.settings.whitewire_threshold_watts} W)")
                dist_pump_should_be_off = False
                break
            else:
                self.log(f"{zone_whitewire_name} is below threshold ({self.data.latest_channel_values[zone_whitewire_name]} <= {self.settings.whitewire_threshold_watts} W)")
        if dist_pump_should_be_off:
            self.log("Dist pump should be off")
            return
        
        if H0CN.dist_flow not in self.data.latest_channel_values or self.data.latest_channel_values[H0CN.dist_flow] is None:
            self.log("Dist flow not found in latest channel values")
            return
        if self.data.latest_channel_values[H0CN.dist_flow]/100 > 0.5:
            self.log(f"The dist pump is on (GPM = {self.data.latest_channel_values[H0CN.dist_flow]/100})")
            if self.pump_doctor_attempts > 0:
                self.log(f"Resetting pump doctor attempts from {self.pump_doctor_attempts} to 0")
                self.pump_doctor_attempts = 0
        else:
            self.log(f"The dist pump is off!! (GPM = {self.data.latest_channel_values[H0CN.dist_flow]/100})")
            if self.time_dist_pump_should_be_on:
                if time.time() - self.time_dist_pump_should_be_on < 3*60:
                    self.log(f"Dist pump should be on for less than 3min ({round((time.time()-self.time_dist_pump_should_be_on)/60)}min)")
                else:
                    self.log(f"Dist pump should be on for more than 3min ({round((time.time()-self.time_dist_pump_should_be_on)/60)}min), starting pump doctor")
                    self.time_dist_pump_should_be_on = None
                    await self.pump_doctor()
            else:
                self.time_dist_pump_should_be_on = time.time()

    async def await_with_watchdog(
        self,
        total_seconds: float,
        pat_every: float = 20.0,
    ):
        """
        Await for total_seconds, patting the internal watchdog periodically.

        IMPORTANT:
        asyncio.sleep() does NOT pat the watchdog.
        Any awaited duration in HomeAlone must go through this helper.
        """
        deadline = time.monotonic() + total_seconds

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            
            await asyncio.sleep(min(pat_every, remaining))
            self.log("Extra h watchdog pat")
            self._send(PatInternalWatchdogMessage(src=self.name))

    async def main(self):
        await asyncio.sleep(5)
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            self.log(f"Top state: {self.top_state}")
            self.log(f"HaStrategy: {self.strategy.value}  |  State: {self.normal_node_state()}")

            # update zone setpoints if just before a new onpeak
            if  self.just_before_onpeak() or self.zone_setpoints=={}:
                self.get_zone_setpoints()
            
            await self.check_dist_pump()

            # No control of actuators when in Monitor
            if not self.top_state == LocalControlTopState.Monitor:
                # update temperatures_available
                self.get_latest_temperatures()

                # Update top state
                if self.top_state == LocalControlTopState.Normal:
                    if self.time_to_trigger_system_cold():
                        self.trigger_system_cold_event()
                elif self.top_state == LocalControlTopState.UsingNonElectricBackup and not self.is_system_cold() and not self.is_onpeak():
                    self.trigger_zones_at_setpoint_offpeak()
                elif self.top_state == LocalControlTopState.ScadaBlind:
                    if self.heating_forecast_available() and self.temperatures_available():
                        self.log("Forecasts and temperatures are both available again!")
                        self.trigger_data_available()
                    elif self.is_onpeak() and self.settings.oil_boiler_backup:
                        if not self.scadablind_boiler:
                            self.aquastat_ctrl_switch_to_boiler(from_node=self.scada_blind_node)
                            self.scadablind_boiler = True
                            self.scadablind_scada = False
                    else:
                        if not self.scadablind_scada:
                            self.aquastat_ctrl_switch_to_scada(from_node=self.scada_blind_node)
                            self.scadablind_boiler = False
                            self.scadablind_scada = True
                
                if self.top_state == LocalControlTopState.Normal:
                    self.engage_brain()
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

    @property
    @abstractmethod
    def temperature_channel_names(self) -> List[str]:
        raise NotImplementedError

    def heating_forecast_available(self) -> bool:
        if self.heating_forecast is None:
            return False
        return True

    def temperatures_available(self) -> bool:
        total_usable_kwh = self.data.latest_channel_values[H0CN.usable_energy]
        required_storage = self.data.latest_channel_values[H0CN.required_energy]
        if total_usable_kwh is None or required_storage is None:
            return False

        all_buffer = [x for x in self.temperature_channel_names if 'buffer-depth' in x]
        available_buffer = [x for x in list(self.latest_temperatures.keys()) if 'buffer-depth' in x]
        if all_buffer == available_buffer:
            return True
        return False

    @abstractmethod
    def time_to_trigger_system_cold(self) -> bool:
        """
        Logic for triggering SystemCold (and moving to top state UsingNonElectricBackup)
        """
        raise NotImplementedError

    @abstractmethod
    def normal_node_state(self) -> str:
        """ Return the state of the 'normal' state machine"""
        raise NotImplementedError

    @abstractmethod
    def is_initializing(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def normal_node_goes_dormant(self) -> None:
        """Trigger GoDormant event"""
        raise NotImplementedError

    @abstractmethod
    def normal_node_wakes_up(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def engage_brain(self) -> None:
        """
        Manages the logic for the Normal top state, (ie. self.state)
        """
        raise NotImplementedError

    @abstractmethod
    def update_relays(self, previous_state) -> None:
        raise NotImplementedError

    def initialize_actuators(self):
        if not self.actuators_ready:
            self.log(f"Waiting to initialize actuators until actuator drivers are ready!")
            return
        self.log("Initializing relays")
        if self.top_state != LocalControlTopState.Normal:
            raise Exception("Can not go into initialize relays if top state is not Normal")
        
        h_normal_relays =  {
            relay
            for relay in self.my_actuators()
            if relay.ActorClass == ActorClass.Relay and
            self.the_boss_of(relay) == self.normal_node
        }

        excluded_relays = {
            self.hp_failsafe_relay,
            self.hp_scada_ops_relay, 
            self.aquastat_control_relay,
            self.hp_loop_on_off,
        }

        if self.strategy == HomeAloneStrategy.WinterTou:
            excluded_relays.add(self.store_charge_discharge_relay)

        target_relays: List[ShNode] = list(h_normal_relays - excluded_relays)
    
        target_relays.sort(key=lambda x: x.Name)
        self.log("de-energizing most relays")
        for relay in target_relays:
            self.de_energize(relay, from_node=self.normal_node)
        self.log("energizing certain critical relays")
        self.hp_failsafe_switch_to_scada(from_node=self.normal_node)
        self.aquastat_ctrl_switch_to_scada(from_node=self.normal_node)
        self.sieg_valve_dormant(from_node=self.normal_node)

        if self.is_onpeak():
            self.log("Is on peak: turning off HP")
            self.turn_off_HP(from_node=self.normal_node)

        try:
            self.log("Setting 010 defaults inside initialize_actuators")
            self.set_010_defaults()
        except ValueError as e:
            self.log(f"Trouble with set_010_defaults: {e}")
        self.actuators_initialized = True

    def trigger_system_cold_event(self) -> None:
        """
        Called to change top state from Normal to UsingNonElectricBackup. Only acts if
          (a) house is actually cold and (b) top state is Normal
        What it does: 
          - changes command tree (all relays will be direct reports of auto.h.backup)
          - triggers SystemCold
          - takes necessary actuator actions to go backup
          - updates the normal state to Dormant if needed
          - reports top state change
        """
        self.set_limited_command_tree(boss=self.backup_node)
        if not self.top_state == LocalControlTopState.Dormant:
            self.normal_node_goes_dormant()
        self.backup_actuator_actions()
        self.trigger_top_event(cause=LocalControlTopStateEvent.SystemCold)    

    def trigger_zones_at_setpoint_offpeak(self):
        """
        Called to change top state from UsingNonElectricBackup to Normal, 
        when backup was started offpeak
        """
        if self.top_state != LocalControlTopState.UsingNonElectricBackup:
            raise Exception("Should only call trigger_zones_at_setpoint_offpeak in transition from UsingNonElectricBackup to Normal!")
        self.trigger_top_event(cause=LocalControlTopStateEvent.CriticalZonesAtSetpointOffpeak)
        self.set_command_tree(boss_node=self.normal_node)
        self.normal_node_wakes_up()

    def trigger_missing_data(self):
        if self.top_state != LocalControlTopState.Normal:
            raise Exception("Should only call trigger_missing_data in transition from Normal to ScadaBlind!")
        self.set_limited_command_tree(boss=self.scada_blind_node)
        self.normal_node_goes_dormant()
        self.scada_blind_actuator_actions()
        self.trigger_top_event(cause=LocalControlTopStateEvent.MissingData)
        self.scadablind_boiler = False
        self.scadablind_scada = False

    def trigger_data_available(self):
        if self.top_state != LocalControlTopState.ScadaBlind:
            raise Exception("Should only call trigger_data_available in transition from ScadaBlind to Normal!")

        self.trigger_top_event(cause=LocalControlTopStateEvent.DataAvailable)
        self.set_command_tree(boss_node=self.normal_node)
        # let the normal homealone know its time to wake up
        self.normal_node_wakes_up()

    def scada_blind_actuator_actions(self) -> None:
        """
        Expects self.scada_blind_node as boss.  Heats with heat pump:
          - turns off store pump
          - iso valve open (valved to discharge)
          - turn hp failsafe to aquastat
        """
        self.turn_off_store_pump(from_node=self.scada_blind_node)
        self.valved_to_discharge_store(from_node=self.scada_blind_node)
        self.hp_failsafe_switch_to_aquastat(from_node=self.scada_blind_node)
        
    def backup_actuator_actions(self) -> None:
        """
        Expects command tree set already with self.backup_node as boss
          - turns off store pump
          - iso valve open (valved to discharge)
          - if using oil boiler, turns hp failsafe to aquastat and aquastat ctrl to boiler
          - if not using oil boiler, turns on heat pump
        """
        self.turn_off_store_pump(from_node=self.backup_node)
        self.valved_to_discharge_store(from_node=self.backup_node)
        if self.settings.oil_boiler_backup:
            self.hp_failsafe_switch_to_aquastat(from_node=self.backup_node)
            self.aquastat_ctrl_switch_to_boiler(from_node=self.backup_node)
        else:
            self.turn_on_HP(from_node=self.backup_node)

    def offpeak_backup_actuator_actions(self) -> None:
        """
        Expects command tree set already with self.offpeak_backup_node as boss
          - turns off store pump
          - iso valve open (valved to discharge)
          - turns hp failsafe to aquastat
        """
        self.turn_off_store_pump(from_node=self.offpeak_backup_node)
        self.valved_to_discharge_store(from_node=self.offpeak_backup_node)
        self.hp_failsafe_switch_to_aquastat(from_node=self.offpeak_backup_node)
        self.aquastat_ctrl_switch_to_boiler(from_node=self.offpeak_backup_node)

    def set_010_defaults(self) -> None:
        """
        Sets default 0-10V values for those actuators that are direct reports
        of the h.n (home alone normal node).
        """
        dfr_component = cast(DfrComponent, self.layout.node(H0N.zero_ten_out_multiplexer).component)
        h_normal_010s = {
            node
            for node in self.my_actuators()
            if node.ActorClass == ActorClass.ZeroTenOutputer and
            self.the_boss_of(node) == self.normal_node
        }

        for dfr_node in h_normal_010s:
            dfr_config = next(
                    config
                    for config in dfr_component.gt.ConfigList
                    if config.ChannelName == dfr_node.name
                )
            self._send_to(
                dst=dfr_node,
                payload=AnalogDispatch(
                    FromGNodeAlias=self.layout.scada_g_node_alias,
                    FromHandle=self.normal_node.handle,
                    ToHandle=dfr_node.handle,
                    AboutName=dfr_node.Name,
                    Value=dfr_config.InitialVoltsTimes100,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=int(time.time() * 1000),
                ),
                src=self.normal_node
            )
            self.log(f"Just set {dfr_node.handle} to {dfr_config.InitialVoltsTimes100} from {self.normal_node.handle} ")

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name="HomeAlone keepalive")
        )

    def stop(self) -> None:
        self._stop_requested = True
        
    async def join(self):
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        match message.Payload:
            case ActuatorsReady():
                self.process_actuators_ready(from_node, message.Payload)
            case GoDormant():
                if len(self.my_actuators()) > 0:
                    raise Exception("HomeAlone sent GoDormant with live actuators under it!")
                if self.top_state != LocalControlTopState.Dormant:
                    # TopGoDormant: Normal/UsingNonElectricBackup -> Dormant
                    self.trigger_top_event(cause=LocalControlTopStateEvent.TopGoDormant)
                    self.normal_node_goes_dormant()
            case WakeUp():
                try:
                    self.process_wake_up(from_node, message.Payload)
                except Exception as e:
                    self.log(f"Trouble with process_wake_up: {e}")
            case HeatingForecast():
                self.log("Received heating forecast")
                self.heating_forecast = message.Payload
                if self.is_initializing():
                    self.log(f"Top state: {self.top_state}")
                    self.log(f"State: {self.normal_node_state()}")
                    self.engage_brain()
        return Ok(True)

    def process_actuators_ready(self, from_node: ShNode, payload: ActuatorsReady) -> None:
        """Move to full send on startup"""
        if not self.actuators_ready:
            self.actuators_ready = True
            self.initialize_actuators()

    def process_wake_up(self, from_node: ShNode, payload: WakeUp) -> None:
        if self.top_state != LocalControlTopState.Dormant:
            return

        # Monitor-only mode: Dormant -> Monitor
        if self.settings.monitor_only:
            self.trigger_top_event(LocalControlTopStateEvent.MonitorOnly)
            self.log("Monitor-only: WakeUp transitioned Dormant -> Monitor")
            return

        # Monitor-only mode: Dormant -> Monitor
        if self.settings.monitor_only:
            self.trigger_top_event(LocalControlTopStateEvent.MonitorOnly)
            self.log("Monitor-only: WakeUp transitioned Dormant -> Monitor")
            return

        # Normal behavior: Dormant -> Normal
        self.trigger_top_event(LocalControlTopStateEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.normal_node)
        # let normal node know its waking up
        self.normal_node_wakes_up()

    def change_all_temps(self, temp_c) -> None:
        if self.is_simulated:
            for channel_name in self.temperature_channel_names:
                self.change_temp(channel_name, temp_c)
        else:
            print("This function is only available in simulation")

    def change_temp(self, channel_name, temp_c) -> None:
        if self.is_simulated:
            self.latest_temperatures[channel_name] = temp_c * 1000
        else:
            print("This function is only available in simulation")

    def get_latest_temperatures(self):
        if not self.is_simulated:
            temp = {
                x: self.data.latest_channel_values[x] 
                for x in self.temperature_channel_names
                if x in self.data.latest_channel_values
                and self.data.latest_channel_values[x] is not None
                }
            self.latest_temperatures = temp.copy()
        else:
            self.log("IN SIMULATION - set all temperatures to 20 degC")
            self.latest_temperatures = {}
            for channel_name in self.temperature_channel_names:
                self.latest_temperatures[channel_name] = 20 * 1000

    def just_before_onpeak(self) -> bool:
        time_now = datetime.now(self.timezone)
        return ((time_now.hour==6 or time_now.hour==16) and time_now.minute>57)
    
    def is_onpeak(self) -> bool:
        time_now = datetime.now(self.timezone)
        time_in_2min = time_now + timedelta(minutes=2)
        peak_hours = [7,8,9,10,11] + [16,17,18,19]
        if (time_now.hour in peak_hours or time_in_2min.hour in peak_hours) and time_now.weekday() < 5:
            return True
        else:
            return False
        
    def is_storage_empty(self):
        if not self.is_simulated:
            if H0CN.usable_energy in self.data.latest_channel_values.keys():
                total_usable_kwh = self.data.latest_channel_values[H0CN.usable_energy] / 1000
            else:
                total_usable_kwh = 0
        else:
            total_usable_kwh = 0
        if total_usable_kwh < 0.2:
            self.log("Storage is empty")
            return True
        else:
            self.log("Storage is not empty")
            return False
        
    def get_zone_setpoints(self):
        if self.is_simulated:
            self.zone_setpoints = {'zone1': 70, 'zone2': 65}
            self.log(f"IN SIMULATION - fake setpoints set to {self.zone_setpoints}")
            return
        self.zone_setpoints = {}
        temps = {}
        for zone_setpoint in [x for x in self.data.latest_channel_values if 'zone' in x and 'set' in x]:
            zone_name = zone_setpoint.replace('-set','')
            zone_name_no_prefix = zone_name[6:] if zone_name[:4]=='zone' else zone_name
            thermal_mass = self.layout.zone_kwh_per_deg_f_list[self.layout.zone_list.index(zone_name_no_prefix)]
            self.log(f"Found zone: {zone_name}, critical: {zone_name_no_prefix in self.layout.critical_zone_list}, thermal mass: {thermal_mass} kWh/degF")
            if self.data.latest_channel_values[zone_setpoint] is not None:
                self.zone_setpoints[zone_name] = self.data.latest_channel_values[zone_setpoint]
            if self.data.latest_channel_values[zone_setpoint.replace('-set','-temp')] is not None:
                temps[zone_name] = self.data.latest_channel_values[zone_setpoint.replace('-set','-temp')]
        self.log(f"Found all zone setpoints: {self.zone_setpoints}")
        self.log(f"Found all zone temperatures: {temps}")
    
    def is_system_cold(self) -> bool:
        """Returns True if at least one critical zones is more than 1F below setpoint, where the 
        setpoint is set at the beginning of the latest onpeak period"""
        if not self.is_onpeak(): #TODO: bleed into the first half hour of offpeak
            self.get_zone_setpoints()
        for zone in self.zone_setpoints:
            zone_name_no_prefix = zone[6:] if zone[:4]=='zone' else zone
            if zone_name_no_prefix not in self.layout.critical_zone_list:
                continue
            setpoint = self.zone_setpoints[zone]
            if not self.is_simulated:
                if zone+'-temp' not in self.data.latest_channel_values:
                    self.log(f"Could not find latest temperature for {zone}!")
                    continue
                temperature = self.data.latest_channel_values[zone+'-temp']
            else:
                temperature = 40
            if temperature < setpoint - 1*1000:
                self.log(f"{zone} temperature is at least 1F lower than the setpoint before starting on-peak")
                return True    
        self.log("All zones are at or above their setpoint at the beginning of on-peak")
        return False

    def to_fahrenheit(self, t:float) -> float:
        return t*9/5+32

    def alert(self, summary: str, details: str) -> None:
        msg =Glitch(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            Node=self.node.Name,
            Type=LogLevel.Critical,
            Summary=summary,
            Details=details
        )
        self._send_to(self.atn, msg)
        self.log(f"CRITICAL GLITCH: {summary}")
