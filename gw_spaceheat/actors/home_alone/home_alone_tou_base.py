import asyncio
from abc import abstractmethod
from typing import List, Optional, Sequence, cast
import time
import uuid
from datetime import datetime, timedelta
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import ActorClass
from gwproto.named_types import AnalogDispatch, SyncedReadings
from result import Ok, Result
from transitions import Machine
from gwsproto.data_classes.house_0_names import H0N, H0CN
from gwproto.data_classes.components.dfr_component import DfrComponent
from actors.scada_actor import ScadaActor
from gwsproto.named_types import (ActuatorsReady,
            GoDormant, Glitch, Ha1Params,
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
    MAX_PUMP_DOCTOR_ATTEMPTS = 3
    MAX_PUMP_WAIT_SECONDS = 60
    ZONE_CONTROL_DELAY_SECONDS = 50
    THRESHOLD_FLOW_GPM_X100 = 50

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
        self.log(f"Params: {self.params}")
        self.log(f"self.is_simulated: {self.is_simulated}")
        self.zone_setpoints = {}
        if H0N.home_alone_normal not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_normal} node!!")
        if H0N.home_alone_scada_blind not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_scada_blind} node!!")
        if H0N.home_alone_backup not in self.layout.nodes:
            raise Exception(f"HomeAlone requires {H0N.home_alone_backup} node!!")
        self.set_command_tree(boss_node=self.normal_node)
        self.actuators_initialized = False
        self.actuators_ready = False

        # State for procedural recovery (non-transactive)
        self.dist_pump_doctor_running = False
        self.dist_pump_doctor_attempts = 0
        self.zone_controller_triggered_at = None
        self.dist_pump_doctor_exhausted = False

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

    async def main(self):
        await asyncio.sleep(5)
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            self.log(f"Top state: {self.top_state}")
            self.log(f"HaStrategy: {self.strategy.value}  |  State: {self.normal_node_state()}")

            # update zone setpoints if just before a new onpeak
            if  self.just_before_onpeak() or self.zone_setpoints=={}:
                self.get_zone_setpoints()

            # Verify distribution pump health; initiate recovery if needed
            if self.needs_dist_pump_recovery():
                await self.dist_pump_doctor()

            # No control of actuators when in Monitor
            if not self.top_state == LocalControlTopState.Monitor:
                self.reconcile_tank_temperatures()

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
        Called to change top state from UsingNonElectricBackup to Normal
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
            case SyncedReadings():
                if self.is_initializing():
                    # buffer temps are in data.latest_channel_values but not
                    # yet in self.latest_temperatures_f
                    self.reconcile_tank_temperatures()
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
        if self.settings.monitor_only:
            self.trigger_top_event(LocalControlTopStateEvent.MonitorOnly)
            self.log("Monitor-only: WakeUp transitioned Dormant -> Monitor")
            return

        # Normal behavior: Dormant -> Normal
        self.trigger_top_event(LocalControlTopStateEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.normal_node)
        # let normal node know its waking up
        self.normal_node_wakes_up()

    # ------------------------------------------------------------------
    # Procedure triggers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Distribution pump monitoring (procedure trigger)
    # ------------------------------------------------------------------

    def needs_dist_pump_recovery(self) -> bool:
        """
        Determine whether the DistPumpDoctor is needed.

        Observes zone calls, flow, and zone-controller startup delay.
        Updates internal timing and attempt counters, but does not
        actuate relays or initiate recovery.
        """
        if self.dist_pump_doctor_running:
            self.log("[DistPumpCheck] Recovery in progress; skipping health check")
            return False

        no_zones_calling = True
        for i in self.h0cn.zone:
            zone_whitewire_name = self.h0cn.zone[i].whitewire_pwr
            if zone_whitewire_name not in self.data.latest_channel_values or self.data.latest_channel_values[zone_whitewire_name] is None:
                self.log(f"[DistPumpCheck] {zone_whitewire_name} was not found in latest channel values.")
                continue
            if abs(self.data.latest_channel_values[zone_whitewire_name]) > self.settings.whitewire_threshold_watts:
                # self.log(f"[DistPumpCheck] {zone_whitewire_name} is above threshold ({self.data.latest_channel_values[zone_whitewire_name]} > {self.settings.whitewire_threshold_watts} W)")
                no_zones_calling = False
                break
            else:
                ...
                # self.log(f"{zone_whitewire_name} is below threshold ({self.data.latest_channel_values[zone_whitewire_name]} <= {self.settings.whitewire_threshold_watts} W)")
        if no_zones_calling:
            # self.log("[Dist pump check] No zones calling; dist pump should be off")
            if self.zone_controller_triggered_at:
                self.log("No zones calling, so clearing zones_controller_triggered_at")
            self.zone_controller_triggered_at = None
            return False

        flow_gpm_x100 = self.data.latest_channel_values.get(H0CN.dist_flow)
        if flow_gpm_x100 is None:
            self.log("[DistPumpCheck] Dist flow not found in latest channel values")
            return False

        # NOTE:
        # Recovery state (attempt counter and exhaustion) is reset when the distribution pump
        # is observed healthy again.
        if flow_gpm_x100 > self.THRESHOLD_FLOW_GPM_X100:
            # self.log(f"[DistPumpCheck] The dist pump is on (GPM = {self.data.latest_channel_values[H0CN.dist_flow]/100})")
            self.zone_controller_triggered_at = None

            if self.dist_pump_doctor_attempts > 0:
                self.log(
                    f"[Dist pump check] Pump running normally (GPM = {flow_gpm_x100 / 100}); resetting pump doctor attempts"
                )

            self.dist_pump_doctor_attempts = 0
            self.dist_pump_doctor_exhausted = False
            return False

        # Pump is OFF but zones are calling

        # The distribution pump is downstream of a zone controller that:
        #   1) Opens zone valves first
        #   2) Waits for end-switch confirmation
        #   3) Only then enables the pump
        #
        # This introduces a normal startup delay (~30–40 seconds) during which
        # SCADA may observe "pump expected ON but no flow".
        #
        # We require the pump to remain OFF beyond this delay before triggering
        # pump_doctor, to avoid false recovery attempts during normal operation.

        if self.zone_controller_triggered_at is None:
            self.zone_controller_triggered_at = time.monotonic()
            self.log("[Dist pump check] Zone controller triggered; awaiting normal valve-open startup delay")
            return False

        elapsed = time.monotonic() - self.zone_controller_triggered_at

        if elapsed <= self.ZONE_CONTROL_DELAY_SECONDS:
            self.log(
                f"[Dist pump check] Still waiting for zone controller startup "
                f"({int(elapsed)}s / {self.ZONE_CONTROL_DELAY_SECONDS}s)"
            )
            return False

        self.log(
            f"[Dist pump check] Startup delay exceeded "
            f"({int(elapsed)}s > {self.ZONE_CONTROL_DELAY_SECONDS}s); triggering pump doctor"
        )

        self.zone_controller_triggered_at = None
        return True


    # ------------------------------------------------------------------
    # Procedural, non-transactive interrupts
    #   - Emit warning glitches when they begin (for auditability)
    #   - Do NOT transition or override the hierarchical state machines
    #   - Designed for short-duration (< ~1 minute) corrective actions
    #   - MUST NOT actuate transactive load control relays
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Procedural utilities (watchdog-safe helpers)
    # ------------------------------------------------------------------

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
            self._send(PatInternalWatchdogMessage(src=self.name))

    async def wait_for_flow(
        self,
        channel: str = H0CN.dist_flow,
        poll_s: float = 2.0,
    ) -> bool:
        """
        Wait for MAX_PUMP_WAIT_SECONDS for flow to exceed THRESHOLD_FLOW_GPM_X100
        channel must be dist_flow, primary_flow or store_flow
        Returns True when flow id detected, False on timeout
        """
        deadline = time.monotonic() + self.MAX_PUMP_WAIT_SECONDS
        if channel not in {H0CN.dist_flow, H0CN.primary_flow, H0CN.store_flow}:
            raise ValueError(f"Unsupported flow channel: {channel}")

        while time.monotonic() < deadline:
            flow = self.data.latest_channel_values.get(channel)
            if flow is not None and flow > self.THRESHOLD_FLOW_GPM_X100:
                return True
            await self.await_with_watchdog(poll_s)
        return False

    # ------------------------------------------------------------------
    # Procederal: Distribution pump recovery
    # ------------------------------------------------------------------

    async def dist_pump_doctor(self):
        # NOTE:
        # pump_doctor runs inline inside the HomeAlone main loop.
        # Any waits here MUST pat the internal watchdog or SCADA will reboot.
        if self.dist_pump_doctor_running:
            self.log("[DistPumpDoctor] Already running, skipping")
            return

        self.dist_pump_doctor_running = True
        try:
            if self.dist_pump_doctor_attempts >= self.MAX_PUMP_DOCTOR_ATTEMPTS:
                if self.dist_pump_doctor_exhausted:
                    return

                self.dist_pump_doctor_exhausted = True
                # Added this bool to only send one critical glitch
                self.log(f"[DistPumpDoctor] Max attempts reached ({self.MAX_PUMP_DOCTOR_ATTEMPTS}), sending critical glitch and giving up")
                self._send_to(
                        self.atn,
                        Glitch(
                            FromGNodeAlias=self.layout.scada_g_node_alias,
                            Node=self.node.Name,
                            Type=LogLevel.Critical,
                            Summary="Dist Pump Failed!!",
                            Details=f"Dist Pump doctor tried {self.dist_pump_doctor_attempts} many times; manual intervention required"
                        )
                    )
                return

            self.log("[DistPumpDoctor] Starting...")
            # Send a warning - will not trigger an alert and gives us a record
            self._send_to(self.atn,
                    Glitch(
                        FromGNodeAlias=self.layout.scada_g_node_alias,
                        Node=self.node.Name,
                        Type=LogLevel.Warning,
                        Summary="DistPumpDoctor starting",
                        Details=f"Attempt {self.dist_pump_doctor_attempts + 1}/{3}"
                    )
                )

            if not self.layout.zone_list:
                self.log("[DistPumpDoctor] Could not find a zone list")
                return

            # Switch all zones to Scada
            self.log("[DistPumpDoctor] Switching zone relays to Scada")
            for zone in self.layout.zone_list:
                self.heatcall_ctrl_to_scada(zone=zone, from_node=self.normal_node)

            # Set DFR to 0
            self.log("[DistPumpDoctor] Setting dist DFR to 0")
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
            await self.await_with_watchdog(5)
            self.log("[DistPumpDoctor] Switching zone relays to Closed")
            for zone in self.layout.zone_list:
                self.stat_ops_close_relay(zone=zone, from_node=self.normal_node)

            # Wait to see flow come in
            self.log("[DistPumpDoctor] Waiting for dist flow")

            flow_detected = await self.wait_for_flow(channel=H0CN.dist_flow)

            if flow_detected:
                self.log("[DistPumpDoctor] Dist flow detected - success!")
                self.dist_pump_doctor_attempts = 0
                self.zone_controller_triggered_at = None
            else:
                self.log(f"[DistPumpDoctor] No dist flow detected within {self.MAX_PUMP_WAIT_SECONDS}s timeout")
                self.dist_pump_doctor_attempts += 1

        except Exception as e:
            self.log(f"[DistPumpDoctor]Internal Error: {e}")
            self._send_to(self.atn,
                    Glitch(
                        FromGNodeAlias=self.layout.scada_g_node_alias,
                        Node=self.node.Name,
                        Type=LogLevel.Warning,
                        Summary="DistPumpDoctor internal error",
                        Details=str(e),
                    )
                )

        finally:
            self.log("[DistPumpDoctor] Setting 0-10V back to default level")
            self.set_010_defaults()
            self.log("[DistPumpDoctor] Switching zones back to thermostat")
            for zone in self.layout.zone_list:
                self.heatcall_ctrl_to_stat(zone=zone, from_node=self.normal_node)
            await self.await_with_watchdog(5)
            self.log("[DistPumpDoctor] Switching scada thermostat relays back to open")
            for zone in self.layout.zone_list:
                self.stat_ops_open_relay(zone=zone, from_node=self.normal_node)
            self.dist_pump_doctor_running = False

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

