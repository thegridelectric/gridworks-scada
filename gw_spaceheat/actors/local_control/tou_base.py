import asyncio
from abc import abstractmethod
from typing import List, Optional, Sequence, cast
import time
import uuid
from datetime import datetime, timedelta
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.named_types import AnalogDispatch, SyncedReadings
from result import Ok, Result
from transitions import Machine
from gwsproto.data_classes.house_0_names import H0N, H0CN
from gwsproto.data_classes.components.dfr_component import DfrComponent

from gwsproto.enums import (
    ActorClass, LocalControlTopEvent,  
    LocalControlTopState, SystemMode,
    SeasonalStorageMode,
)
from gwsproto.named_types import (ActuatorsReady,
            GoDormant,  Ha1Params,
            NewCommandTree, SingleMachineState, WakeUp)

from actors.procedural.dist_pump_doctor import DistPumpDoctor
from actors.procedural.dist_pump_monitor import DistPumpMonitor

from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface


class LocalControlTouBase(ShNodeActor):
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

        self._stop_requested: bool = False
        self.hardware_layout = self._services.hardware_layout
        
        self.time_since_blind: Optional[float] = None
        self.scadablind_scada = False
        self.scadablind_boiler = False

        self.top_machine = Machine(
            model=self,
            states=LocalControlTouBase.top_states,
            transitions=LocalControlTouBase.top_transitions,
            initial=LocalControlTopState.Normal,
            send_event=False,
            model_attribute="top_state",
        )  
        if self.settings.system_mode == SystemMode.MonitorOnly:
            self.top_state = LocalControlTopState.Monitor
        else: 
            self.top_state = LocalControlTopState.Normal
        self.is_simulated = self.settings.is_simulated
        self.log(f"Params: {self.params}")
        self.log(f"self.is_simulated: {self.is_simulated}")
        self.zone_setpoints = {}
        if H0N.local_control_normal not in self.layout.nodes:
            raise Exception(f"LocalControl requires {H0N.local_control_normal} node!!")
        if H0N.local_control_scada_blind not in self.layout.nodes:
            raise Exception(f"LocalControl requires {H0N.local_control_scada_blind} node!!")
        if H0N.local_control_backup not in self.layout.nodes:
            raise Exception(f"LocalControl requires {H0N.local_control_backup} node!!")
        self.set_command_tree(boss_node=self.normal_node)
        self.actuators_initialized = False
        self.actuators_ready = False
        self.dist_pump_doctor = DistPumpDoctor(host=self)
        self.dist_pump_monitor = DistPumpMonitor(host=self,doctor=self.dist_pump_doctor)



    @property
    def normal_node(self) -> ShNode:
        return self.layout.local_control_normal_node

    @property
    def backup_node(self) -> ShNode:
        """ 
        The node / state machine responsible
        for backup operations
        """
        return self.layout.local_control_backup_node

    @property
    def scada_blind_node(self) -> ShNode:
        """
        THe node / state machine responsible
        for when the scada has missing data (forecasts / temperatures)
        """
        return self.layout.local_control_scada_blind_node

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
            raise ValueError("Cannot set limited command tree: boss node is None")
        
        for node in self.my_actuators():
            node.Handle = f"{boss.Handle}.{node.Name}"
        self._send_to(
            self.ltn,
            NewCommandTree(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                ShNodes=list(self.layout.nodes.values()),
                UnixMs=int(time.time() * 1000),
            ),
        )
        self.log(f"Set ha command tree w all actuators reporting to {boss.handle}")

    def trigger_top_event(self, cause: LocalControlTopEvent) -> None:
        """
        Trigger top event. Set relays_initialized to False if top state
        is Dormant. Report state change.
        """
        orig_state = self.top_state
        now_ms = int(time.time() * 1000)
        if cause == LocalControlTopEvent.SystemCold:
            self.SystemCold()
        elif cause == LocalControlTopEvent.TopGoDormant:
            self.TopGoDormant()
        elif cause == LocalControlTopEvent.TopWakeUp:
            self.TopWakeUp()
        elif cause == LocalControlTopEvent.MissingData:
            self.MissingData()
        elif cause == LocalControlTopEvent.DataAvailable:
            self.DataAvailable()
        elif cause == LocalControlTopEvent.MonitorOnly:
            self.MonitorOnly()
        elif cause == LocalControlTopEvent.MonitorAndControl:
            self.MonitorAndControl()
        elif cause == LocalControlTopEvent.CriticalZonesAtSetpointOffpeak:
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

    async def main(self):
        await asyncio.sleep(5)
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            self.log(f"Top state: {self.top_state}")
            self.log(f"LocalControl: {self.settings.seasonal_storage_mode}  |  State: {self.normal_node_state()}")

            if self.top_state == LocalControlTopState.Dormant:
                await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)
                continue

            # update zone setpoints if just before a new onpeak
            if  self.just_before_onpeak() or self.zone_setpoints=={}:
                self.get_zone_setpoints()

            # Verify distribution pump health; initiate recovery if needed
            if self.dist_pump_monitor.needs_recovery():
                await self.dist_pump_doctor.run()

            # No control of actuators when in Monitor
            if not self.top_state == LocalControlTopState.Monitor:
                self.get_temperatures()

                # Update top state
                if self.top_state == LocalControlTopState.Normal:
                    if self.time_to_trigger_system_cold():
                        self.trigger_system_cold_event()
                elif self.top_state == LocalControlTopState.UsingNonElectricBackup and not self.is_system_cold() and not self.is_onpeak():
                    self.trigger_zones_at_setpoint_offpeak()
                elif self.top_state == LocalControlTopState.ScadaBlind:
                    if self.heating_forecast and self.buffer_temps_available:
                        self.log("Forecasts and temperatures are both available again!")
                        self.trigger_data_available()
                    elif self.is_onpeak() and self.settings.oil_boiler_backup:
                        if not self.scadablind_boiler:
                            self.aquastat_ctrl_switch_to_boiler(from_node=self.scada_blind_node)
                            self.scadablind_boiler = True
                            self.scadablind_scada = False
                            self.log("ScadaBlind: switching to boiler onpeak")
                    else:
                        if not self.scadablind_scada:
                            self.aquastat_ctrl_switch_to_scada(from_node=self.scada_blind_node)
                            self.scadablind_boiler = False
                            self.scadablind_scada = True
                            self.log("ScadaBlind: switching to Aqaustatically controlled SCADA offpeak")
                
                if self.top_state == LocalControlTopState.Normal:
                    self.engage_brain()
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

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
            self.log("Waiting to initialize actuators until actuator drivers are ready!")
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

        if self.settings.seasonal_storage_mode == SeasonalStorageMode.AllTanks:
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
        self.trigger_top_event(cause=LocalControlTopEvent.SystemCold)    

    def trigger_zones_at_setpoint_offpeak(self):
        """
        Called to change top state from UsingNonElectricBackup to Normal
        """
        if self.top_state != LocalControlTopState.UsingNonElectricBackup:
            raise Exception("Should only call trigger_zones_at_setpoint_offpeak in transition from UsingNonElectricBackup to Normal!")
        self.trigger_top_event(cause=LocalControlTopEvent.CriticalZonesAtSetpointOffpeak)
        self.set_command_tree(boss_node=self.normal_node)
        self.normal_node_wakes_up()

    def trigger_missing_data(self):
        if self.top_state != LocalControlTopState.Normal:
            raise Exception("Should only call trigger_missing_data in transition from Normal to ScadaBlind!")
        self.set_limited_command_tree(boss=self.scada_blind_node)
        self.normal_node_goes_dormant()
        self.scada_blind_actuator_actions()
        self.trigger_top_event(cause=LocalControlTopEvent.MissingData)
        self.scadablind_boiler = False
        self.scadablind_scada = False

    def trigger_data_available(self):
        if self.top_state != LocalControlTopState.ScadaBlind:
            raise Exception("Should only call trigger_data_available in transition from ScadaBlind to Normal!")

        self.trigger_top_event(cause=LocalControlTopEvent.DataAvailable)
        self.set_command_tree(boss_node=self.normal_node)
        # let the normal localcontrol know its time to wake up
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
            asyncio.create_task(self.main(), name="LocalControl keepalive")
        )

    def stop(self) -> None:
        self._stop_requested = True
        
    async def join(self):
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(True)
        match message.Payload:
            case ActuatorsReady():
                self.process_actuators_ready(from_node, message.Payload)
            case GoDormant():
                if len(self.my_actuators()) > 0:
                    raise Exception("LocalControl sent GoDormant with live actuators under it!")
                if self.top_state != LocalControlTopState.Dormant:
                    # TopGoDormant: Normal/UsingNonElectricBackup -> Dormant
                    self.trigger_top_event(cause=LocalControlTopEvent.TopGoDormant)
                    self.normal_node_goes_dormant()
            case WakeUp():
                try:
                    self.process_wake_up(from_node, message.Payload)
                except Exception as e:
                    self.log(f"Trouble with process_wake_up: {e}")
            case SyncedReadings():
                if self.is_initializing():
                    # buffer temps are in data.latest_channel_values but not
                    # yet in self.latest_temperatures_f
                    self.get_temperatures()
                    self.log(f"Buffer Temps Available: {self.buffer_temps_available}")
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
        if self.settings.system_mode == SystemMode.MonitorOnly:
            # MonitorOnly: SCADA must not actuate anything
            self.trigger_top_event(LocalControlTopEvent.MonitorOnly)
            self.log("Monitor-only: WakeUp transitioned Dormant -> Monitor")
            return

        # Normal behavior: Dormant -> Normal
        self.trigger_top_event(LocalControlTopEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.normal_node)
        # let normal node know its waking up
        self.normal_node_wakes_up()

    # ------------------------------------------------------------------
    # utilities
    # ------------------------------------------------------------------

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
        if self.usable_kwh < 0.2:
            return True
        else:
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
            # self.log(f"Found zone: {zone_name}, critical: {zone_name_no_prefix in self.layout.critical_zone_list}, thermal mass: {thermal_mass} kWh/degF")
            if self.data.latest_channel_values[zone_setpoint] is not None:
                self.zone_setpoints[zone_name] = self.data.latest_channel_values[zone_setpoint]
            if self.data.latest_channel_values[zone_setpoint.replace('-set','-temp')] is not None:
                temps[zone_name] = self.data.latest_channel_values[zone_setpoint.replace('-set','-temp')]
        # self.log(f"Found all zone setpoints: {self.zone_setpoints}")
        # self.log(f"Found all zone temperatures: {temps}")
    
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

