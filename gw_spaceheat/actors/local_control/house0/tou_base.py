import asyncio
from abc import abstractmethod
from typing import List, Optional, Sequence
import time
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.named_types import SyncedReadings
from result import Ok, Result
from transitions import Machine
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)

from gwsproto.enums import (
    ActorClass, LocalControlTopEvent,
    LocalControlTopState,
)
from gwsproto.named_types import (ActuatorsReady,
            GoDormant,  Ha1Params,
            SingleMachineState, WakeUp)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.house0.node_names import House0NodeNames

from actors.procedural.dist_pump_doctor import DistPumpDoctor
from actors.procedural.dist_pump_monitor import DistPumpMonitor
from actors.procedural.store_pump_doctor import StorePumpDoctor
from actors.procedural.store_pump_monitor import StorePumpMonitor

from actors.hydronic.house0 import House0Hydronic
from actors.in_process_messages import HouseCold, HouseWarm
from scada_app_interface import ScadaAppInterface


class LocalControlTouBase(House0Hydronic):
    """Manages the top level state machine for home alone in a time of use framework. Every home 
    alone node has a strategy. That strategy is in charge of how the "normal" home alone code works. Strategy-specific code
    should inherit from this base class."""
    MAIN_LOOP_SLEEP_SECONDS = 60
    BLIND_MINUTES = 5


    COLD_STATES = (LocalControlTopState.InBackup, LocalControlTopState.ColdOverride)
    top_states = [
        LocalControlTopState.Dormant,
        LocalControlTopState.InBackup,
        LocalControlTopState.ColdOverride,
        LocalControlTopState.Normal,
        LocalControlTopState.ScadaBlind,
    ]
    top_transitions = [
        {"trigger": "TopGoDormant", "source": "Normal", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "InBackup", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "ColdOverride", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "ScadaBlind", "dest": "Dormant"},
        {"trigger": "TopWakeUp", "source": "Dormant", "dest": "Normal"},
        {"trigger": "SystemCold", "source": "Normal", "dest": "InBackup"},
        {"trigger": "SystemColdNoBackup", "source": "Normal", "dest": "ColdOverride"},
        {"trigger": "CriticalZonesAtSetpointOffpeak", "source": "InBackup", "dest": "Normal"},
        {"trigger": "CriticalZonesAtSetpointOffpeak", "source": "ColdOverride", "dest": "Normal"},
        {"trigger": "MissingData", "source": "Normal", "dest": "ScadaBlind"},
        {"trigger": "DataAvailable", "source": "ScadaBlind", "dest": "Normal"},
    ]

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)

        self._stop_requested: bool = False
        self.hardware_layout = self._services.hardware_layout
        
        self.time_since_blind: Optional[float] = None
        self.house_cold = False
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
        self.top_state = LocalControlTopState.Normal
        self.log(f"Params: {self.params}")
        self.set_command_tree(boss_node=self.normal_node)
        self.actuators_initialized = False
        self.actuators_ready = False
        self.dist_pump_doctor = DistPumpDoctor(host=self)
        self.dist_pump_monitor = DistPumpMonitor(host=self,doctor=self.dist_pump_doctor)
        self.store_pump_doctor = StorePumpDoctor(host=self)
        self.store_pump_monitor = StorePumpMonitor(host=self,doctor=self.store_pump_doctor)
        self.dist_pump_recovery_enabled = self._dist_pump_recovery_enabled()
        self.store_pump_recovery_enabled = self._store_pump_recovery_enabled()
        if not self.dist_pump_recovery_enabled:
            self.log("Dist pump recovery disabled: required relay/010V nodes are not present in layout")
        if not self.store_pump_recovery_enabled:
            self.log("Store pump recovery disabled: required relay/010V nodes are not present in layout")


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
    def cold_override_node(self) -> ShNode:
        """
        The node / state machine that runs the heat pump through the
        peak because the house is cold
        """
        return self.layout.local_control_cold_override_node

    def uses_backup_when_cold(self) -> bool:
        return self.ops.UsesBackupWhenCold

    @property
    def cold_state_node(self) -> ShNode:
        """The node that commands when the house is cold"""
        if self.uses_backup_when_cold():
            return self.backup_node
        return self.cold_override_node

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

    def trigger_top_event(self, cause: LocalControlTopEvent) -> None:
        """
        Trigger top event. Set relays_initialized to False if top state
        is Dormant. Report state change.
        """
        orig_state = self.top_state
        now_ms = int(time.time() * 1000)
        if cause == LocalControlTopEvent.SystemCold:
            self.SystemCold()
        elif cause == LocalControlTopEvent.SystemColdNoBackup:
            self.SystemColdNoBackup()
        elif cause == LocalControlTopEvent.TopGoDormant:
            self.TopGoDormant()
        elif cause == LocalControlTopEvent.TopWakeUp:
            self.TopWakeUp()
        elif cause == LocalControlTopEvent.MissingData:
            self.MissingData()
        elif cause == LocalControlTopEvent.DataAvailable:
            self.DataAvailable()
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

    def _has_layout_nodes(self, names: list[str]) -> bool:
        return all(self.layout.node(name) is not None for name in names)

    def _dist_pump_recovery_enabled(self) -> bool:
        # The circuits' relays are required actuators (gw.house0.layout
        # RequiredActuators), so the 0-10V output is the one that can be absent.
        return self._has_layout_nodes([HSNN.dist_010v])

    def _store_pump_recovery_enabled(self) -> bool:
        return self._has_layout_nodes(
            [
                HSNN.store_010v,
                House0NodeNames.store_charge_discharge_relay,
                HSNN.store_pump_relay,
            ]
        )

    async def main(self):
        await asyncio.sleep(5)
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            self.log(f"Top state: {self.top_state}")
            self.log(f"LocalControl: {self.ops.FamilyParams.SeasonalStorageMode}  |  State: {self.normal_node_state()}")

            if self.top_state == LocalControlTopState.Dormant:
                await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)
                continue

            # update zone setpoints if just before a new onpeak
            if  self.just_before_onpeak() or self.setpoints_at_onpeak_start=={}:
                self.refresh_setpoints_at_onpeak_start()

            # Verify distribution pump health; initiate recovery if needed
            if self.dist_pump_recovery_enabled and self.dist_pump_monitor.needs_recovery():
                await self.dist_pump_doctor.run()

            # Verify store pump health; initiate recovery if needed
            if self.store_pump_recovery_enabled and self.store_pump_monitor.needs_recovery():
                await self.store_pump_doctor.run()

            self.get_temperatures()

            # Update top state
            if self.top_state in self.COLD_STATES and not self.house_cold and not self.is_onpeak():
                self.trigger_zones_at_setpoint_offpeak()
            elif self.top_state == LocalControlTopState.ScadaBlind:
                if self.heating_forecast and self.buffer_temps_available:
                    self.log("Forecasts and temperatures are both available again!")
                    self.trigger_data_available()
                elif self.is_onpeak() and self.ops.UsesBackupWhenCold:
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

    @property
    def command_node(self) -> ShNode:
        """
        top of command tree

        This is used by procedural, non-transactive interrupts.
        Always returns an ShNode, even if authority is degraded.
        """
        if self.top_state == LocalControlTopState.ScadaBlind:
            return self.scada_blind_node

        if self.top_state == LocalControlTopState.InBackup:
            return self.backup_node

        if self.top_state == LocalControlTopState.ColdOverride:
            return self.cold_override_node

        return self.normal_node

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
            self.layout.hp_failsafe_relay,
            self.layout.hp_scada_ops_relay, 
            self.layout.aquastat_control_relay,
            self.layout.hp_loop_on_off,
        }

        target_relays: List[ShNode] = list(h_normal_relays - excluded_relays)
    
        target_relays.sort(key=lambda x: x.Name)
        self.log("de-energizing most relays")
        for relay in target_relays:
            self.de_energize(relay, from_node=self.normal_node)
        self.log("energizing certain critical relays")
        self.hp_failsafe_switch_to_scada(from_node=self.normal_node)
        self.aquastat_ctrl_switch_to_scada(from_node=self.normal_node)

        if self.is_onpeak():
            self.log("Is on peak: turning off HP")
            self.turn_off_hp(from_node=self.normal_node)

        try:
            self.log("Setting 010 defaults inside initialize_actuators")
            self.set_010_defaults(command_node=self.command_node)
        except ValueError as e:
            self.log(f"Trouble with set_010_defaults: {e}")
        self.actuators_initialized = True

    def trigger_system_cold_event(self) -> None:
        """
        Called on the cold watch's HouseCold to change top state from
        Normal to InBackup or ColdOverride, by whether the house uses its
        backup when cold.
        What it does:
          - changes command tree (the cold state's node is the boss)
          - updates the normal state to Dormant if needed
          - takes the actuator actions of the cold state
          - triggers SystemCold or SystemColdNoBackup
          - reports top state change
        """
        self.set_command_tree(boss_node=self.cold_state_node)
        if not self.top_state == LocalControlTopState.Dormant:
            self.normal_node_goes_dormant()
        if self.uses_backup_when_cold():
            self.backup_actuator_actions()
            self.trigger_top_event(cause=LocalControlTopEvent.SystemCold)
        else:
            self.cold_override_actuator_actions()
            self.trigger_top_event(cause=LocalControlTopEvent.SystemColdNoBackup)

    def trigger_zones_at_setpoint_offpeak(self):
        """
        Called to change top state from InBackup or ColdOverride to Normal
        """
        if self.top_state not in self.COLD_STATES:
            raise Exception("Should only call trigger_zones_at_setpoint_offpeak in transition from a cold state to Normal!")
        self.trigger_top_event(cause=LocalControlTopEvent.CriticalZonesAtSetpointOffpeak)
        self.set_command_tree(boss_node=self.normal_node)
        self.normal_node_wakes_up()

    def trigger_missing_data(self):
        if self.top_state != LocalControlTopState.Normal:
            raise Exception("Should only call trigger_missing_data in transition from Normal to ScadaBlind!")
        self.set_command_tree(boss_node=self.scada_blind_node)
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
        self.turn_off_store_pump(command_node=self.scada_blind_node)
        self.valved_to_discharge_store(from_node=self.scada_blind_node)
        self.hp_failsafe_switch_to_aquastat(from_node=self.scada_blind_node)
        
    def backup_actuator_actions(self) -> None:
        """
        Expects command tree set already with self.backup_node as boss
          - turns off store pump
          - iso valve open (valved to discharge)
          - turns hp failsafe to aquastat and aquastat ctrl to boiler
        """
        self.turn_off_store_pump(command_node=self.backup_node)
        self.valved_to_discharge_store(from_node=self.backup_node)
        self.hp_failsafe_switch_to_aquastat(from_node=self.backup_node)
        self.aquastat_ctrl_switch_to_boiler(from_node=self.backup_node)

    def cold_override_actuator_actions(self) -> None:
        """
        Expects command tree set already with self.cold_override_node as boss
          - turns off store pump
          - iso valve open (valved to discharge)
          - turns on heat pump
        """
        self.turn_off_store_pump(command_node=self.cold_override_node)
        self.valved_to_discharge_store(from_node=self.cold_override_node)
        self.turn_on_hp(from_node=self.cold_override_node)

    def start(self) -> None:
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=LocalControlTopState.enum_name(),
                State=self.top_state,
                UnixMs=int(time.time() * 1000),
            ),
        )
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
            case HouseCold():
                self.house_cold = True
                if self.top_state == LocalControlTopState.Normal:
                    self.trigger_system_cold_event()
            case HouseWarm():
                self.house_cold = False
                if self.top_state in self.COLD_STATES and not self.is_onpeak():
                    self.trigger_zones_at_setpoint_offpeak()
            case GoDormant():
                if len(self.my_actuators()) > 0:
                    raise Exception("LocalControl sent GoDormant with live actuators under it!")
                if self.top_state != LocalControlTopState.Dormant:
                    # TopGoDormant: Normal/InBackup/ColdOverride/ScadaBlind -> Dormant
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

        # Normal behavior: Dormant -> Normal
        self.trigger_top_event(LocalControlTopEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.normal_node)
        # let normal node know its waking up
        self.normal_node_wakes_up()

