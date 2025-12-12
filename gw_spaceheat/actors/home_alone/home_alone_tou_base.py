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
from gwsproto.enums import HomeAloneStrategy, HomeAloneTopState, LogLevel
from scada_app_interface import ScadaAppInterface


class TopStateEvent(GwStrEnum):
    HouseColdOnpeak = auto()
    TopGoDormant = auto()
    TopWakeUp = auto()
    JustOffpeak = auto()
    MissingData = auto()
    DataAvailable = auto()
    MonitorOnly = auto()
    MonitorAndControl = auto()

class HomeAloneTouBase(ScadaActor):
    """Manages the top level state machine for home alone in a time of use framework. Every home 
    alone node has a strategy. That strategy is in charge of how the "normal" home alone code works. Strategy-specific code
    should inherit from this base class."""
    MAIN_LOOP_SLEEP_SECONDS = 60
    BLIND_MINUTES = 5


    top_states = HomeAloneTopState.values()
    # ["Normal", "UsingBackupOnpeak", "Dormant", "ScadaBlind", "Monitor"]
    top_transitions = [
        {"trigger": "HouseColdOnpeak", "source": "Normal", "dest": "UsingBackupOnpeak"},
        {"trigger": "TopGoDormant", "source": "Normal", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "UsingBackupOnpeak", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "ScadaBlind", "dest": "Dormant"},
        {"trigger": "TopWakeUp", "source": "Dormant", "dest": "Normal"},
        {"trigger": "JustOffpeak", "source": "UsingBackupOnpeak", "dest": "Normal"},
        {"trigger": "MissingData", "source": "Normal", "dest": "ScadaBlind"},
        {"trigger": "DataAvailable", "source": "ScadaBlind", "dest": "Normal"},
        {"trigger": "MonitorOnly", "source": "Normal", "dest": "Monitor"},
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
            initial=HomeAloneTopState.Normal,
            send_event=False,
            model_attribute="top_state",
        )  
        if self.settings.monitor_only:
            self.top_state = HomeAloneTopState.Monitor
        else: 
            self.top_state = HomeAloneTopState.Normal
        self.is_simulated = self.settings.is_simulated
        self.oil_boiler_during_onpeak = self.settings.oil_boiler_for_onpeak_backup
        self.log(f"Params: {self.params}")
        self.log(f"self.is_simulated: {self.is_simulated}")
        self.heating_forecast: Optional[HeatingForecast] = None
        self.zone_setpoints = {}
        if H0N.home_alone_normal not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_normal} node!!")
        if H0N.home_alone_scada_blind not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_scada_blind} node!!")
        if H0N.home_alone_onpeak_backup not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_onpeak_backup} node!!")
        self.set_command_tree(boss_node=self.normal_node)
        self.latest_temperatures: Dict[str, int] = {} # 
        self.actuators_initialized = False
        self.actuators_ready = False
        self.pump_doctor_attempts = 0
        self.time_dist_pump_should_be_on = None

    @property
    def normal_node(self) -> ShNode:
        """
        Overwrite the standard 
        """
        return self.layout.node(H0N.home_alone_normal)

    @property
    def onpeak_backup_node(self) -> ShNode:
        """ 
        The node / state machine responsible
        for onpeak backup operations
        """
        return self.layout.node(H0N.home_alone_onpeak_backup)

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

    def trigger_top_event(self, cause: TopStateEvent) -> None:
        """
        Trigger top event. Set relays_initialized to False if top state
        is Dormant. Report state change.
        """
        orig_state = self.top_state
        now_ms = int(time.time() * 1000)
        if cause == TopStateEvent.HouseColdOnpeak:
            self.HouseColdOnpeak()
        elif cause == TopStateEvent.TopGoDormant:
            self.TopGoDormant()
        elif cause == TopStateEvent.TopWakeUp:
            self.TopWakeUp()
        elif cause == TopStateEvent.JustOffpeak:
            self.JustOffpeak()
        elif cause == TopStateEvent.MissingData:
            self.MissingData()
        elif cause == TopStateEvent.DataAvailable:
            self.DataAvailable()
        elif cause == TopStateEvent.MonitorOnly:
            self.MonitorOnly()
        elif cause == TopStateEvent.MonitorAndControl:
            self.MonitorAndControl()
        else:
            raise Exception(f"Unknown top event {cause}")
        
        self.log(f"Top State {cause.value}: {orig_state} -> {self.top_state}")
        if self.top_state == HomeAloneTopState.Normal:
            self.actuators_initialized = False
            self.log(f"need to initialize actuators again")

        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=HomeAloneTopState.enum_name(),
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
        self.log("[Pump doctor] Starting...")
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
        self.log("[Pump doctor] Switching zone relays to Closed...")
        for zone in self.layout.zone_list:
            self.stat_ops_close_relay(zone=zone, from_node=self.normal_node)

        # Wait to see flow come in
        self.log(f"[Pump doctor] Waiting 1 minute")
        await asyncio.sleep(int(1*60))

        # Check if dist flow is detected, if yes switch all zones back Open and Thermostat
        if H0CN.dist_flow not in self.data.latest_channel_values or self.data.latest_channel_values[H0CN.dist_flow] is None:
            self.log("[Pump doctor] Dist flow not found in latest channel values")
            return
        if self.data.latest_channel_values[H0CN.dist_flow]/100 > 0.5:
            self.log('[Pump doctor] Dist flow detected - success!')
            self.log(f"[Pump doctor] Switching zones back to Open and Thermostat")
            self.pump_doctor_attempts = 0
            for zone in self.layout.zone_list:
                self.stat_ops_open_relay(zone=zone, from_node=self.normal_node)
                self.heatcall_ctrl_to_stat(zone=zone, from_node=self.normal_node)  
        else:
            self.log('[Pump doctor] No dist flow detected - did not work')
            self.pump_doctor_attempts += 1
        
    async def check_dist_pump(self):
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
            self.time_dist_pump_should_be_on = None
            return
        
        if not self.time_dist_pump_should_be_on:
            self.time_dist_pump_should_be_on = time.time()
        if time.time() - self.time_dist_pump_should_be_on < 3*60:
            self.log(f"Dist pump should be on since less than 3min ({round((time.time()-self.time_dist_pump_should_be_on)/60)}min)")
            return
        
        self.log(f"Dist pump should be on since {round((time.time()-self.time_dist_pump_should_be_on)/60)}min")
        if H0CN.dist_flow not in self.data.latest_channel_values or self.data.latest_channel_values[H0CN.dist_flow] is None:
            self.log("Dist flow not found in latest channel values")
            return
        if self.data.latest_channel_values[H0CN.dist_flow]/100 > 0.5:
            self.log(f"The dist pumps in on (GPM = {self.data.latest_channel_values[H0CN.dist_flow]/100})")
        else:
            self.log(f"The dist pumps in off!! (GPM = {self.data.latest_channel_values[H0CN.dist_flow]/100})")
            await self.pump_doctor()

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

            if not self.top_state == HomeAloneTopState.Monitor:
                # update temperatures_available
                self.get_latest_temperatures()

                # Update top state
                if self.top_state == HomeAloneTopState.Normal:
                    if self.time_to_trigger_house_cold_onpeak():
                        self.trigger_house_cold_onpeak_event()
                        if self.strategy == HomeAloneStrategy.ShoulderTou:
                            self.alert("Onpeak oil boiler", "House cold on peak, backup oil boiler")
                elif self.top_state == HomeAloneTopState.UsingBackupOnpeak and not self.is_onpeak():
                    self.trigger_just_offpeak()
                elif self.top_state == HomeAloneTopState.ScadaBlind:
                    if self.heating_forecast_available() and self.temperatures_available():
                        self.log("Forecasts and temperatures are both available again!")
                        self.trigger_data_available()
                    elif self.is_onpeak() and self.settings.oil_boiler_for_onpeak_backup:
                        if not self.scadablind_boiler:
                            self.aquastat_ctrl_switch_to_boiler(from_node=self.scada_blind_node)
                            self.scadablind_boiler = True
                            self.scadablind_scada = False
                    else:
                        if not self.scadablind_scada:
                            self.aquastat_ctrl_switch_to_scada(from_node=self.scada_blind_node)
                            self.scadablind_boiler = False
                            self.scadablind_scada = True
                
                if self.top_state == HomeAloneTopState.Normal:
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
    def time_to_trigger_house_cold_onpeak(self) -> bool:
        """
        Logic for triggering HouseColdOnpeak (and moving to top state UsingBakupOnpeak)
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
        if self.top_state != HomeAloneTopState.Normal:
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

    def trigger_house_cold_onpeak_event(self) -> None:
        """
        Called to change top state from Normal to HouseColdOnpeak. Only acts if
          (a) house is actually cold onpeak and (b) top state is Normal
        What it does: 
          - changes command tree (all relays will be direct reports of auto.h.onpeak-backup)
          - triggers HouseColdOnpeak
          - takes necessary actuator actions to go onpeak
          - updates the normal state to Dormant if needed
          - reports top state change

        """
        self.set_limited_command_tree(boss=self.onpeak_backup_node)
        if not self.top_state == HomeAloneTopState.Dormant:
            self.normal_node_goes_dormant()
        self.onpeak_backup_actuator_actions()
        self.trigger_top_event(cause=TopStateEvent.HouseColdOnpeak)    

    def trigger_just_offpeak(self):
        """
        Called to change top state from HouseColdOnpeak to Normal
        What it does:
            - flip relays as needed
            - trigger the top state change
            - change 
        """
        # HouseColdOnpeak: Normal -> UsingBackupOnpeak
        if self.top_state != HomeAloneTopState.UsingBackupOnpeak:
            raise Exception("Should only call leave_onpeak_backup in transition from UsingBackupOnpeak to Normal!")

        # Report state change to scada
        self.trigger_top_event(cause=TopStateEvent.JustOffpeak)
        # implement the change in command tree. Boss: h.onpeak-backup -> h.n
        self.set_command_tree(boss_node=self.normal_node)
        # let the normal homealone know its time to wake up
        self.normal_node_wakes_up()

    def trigger_missing_data(self):
        if self.top_state != HomeAloneTopState.Normal:
            raise Exception("Should only call trigger_missing_data in transition from Normal to ScadaBlind!")
        self.set_limited_command_tree(boss=self.scada_blind_node)
        # let the normal node know its time to go dormant
        self.normal_node_goes_dormant()
        
        self.scada_blind_actuator_actions()
        self.trigger_top_event(cause=TopStateEvent.MissingData)
        self.scadablind_boiler = False
        self.scadablind_scada = False

    def trigger_data_available(self):
        if self.top_state != HomeAloneTopState.ScadaBlind:
            raise Exception("Should only call trigger_data_available in transition from ScadaBlind to Normal!")

        self.trigger_top_event(cause=TopStateEvent.DataAvailable)
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
        
    def onpeak_backup_actuator_actions(self) -> None:
        """
        Expects command tree set already with self.onpeak_backup_node as boss
          - turns off store pump
          - iso valve open (valved to discharge)
          - if using oil boiler, turns hp failsafe to aquastat and aquastat ctrl to boiler
          - if not using oil boiler, turns on heat pump

        """
        self.turn_off_store_pump(from_node=self.onpeak_backup_node)
        self.valved_to_discharge_store(from_node=self.onpeak_backup_node)
        if self.settings.oil_boiler_for_onpeak_backup:
            self.hp_failsafe_switch_to_aquastat(from_node=self.onpeak_backup_node)
            self.aquastat_ctrl_switch_to_boiler(from_node=self.onpeak_backup_node)
        else:
            self.turn_on_HP(from_node=self.onpeak_backup_node)

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
                if self.top_state != HomeAloneTopState.Dormant:
                    # TopGoDormant: Normal/UsingBackupOnpeak -> Dormant
                    self.trigger_top_event(cause=TopStateEvent.TopGoDormant)
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
        if self.top_state != HomeAloneTopState.Dormant:
            return
        # TopWakeUp: Dormant -> Normal
        self.trigger_top_event(TopStateEvent.TopWakeUp)
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
    
    def is_house_cold(self) -> bool:
        """Returns True if at least one critical zones is more than 1F below setpoint, where the 
        setpoint is set at the beginning of the latest onpeak period"""
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
