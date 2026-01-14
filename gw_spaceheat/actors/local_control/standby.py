import asyncio
from typing import List, Optional, Sequence
import time
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import SystemMode
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from gwsproto.enums import ActorClass
from gwproto import Message
from result import Ok, Result
from gwsproto.enums import LocalControlStandbyTopState, LocalControlStandbyTopEvent
from gwsproto.named_types import SingleMachineState
from gwsproto.data_classes.sh_node import ShNode
from transitions import Machine
from actors.sh_node_actor import ShNodeActor
from gwsproto.named_types import ActuatorsReady, GoDormant, HeatingForecast, WakeUp
from scada_app_interface import ScadaAppInterface

class StandbyLocalControl(ShNodeActor):
    MAIN_LOOP_SLEEP_SECONDS = 300
    top_states = LocalControlStandbyTopState.values()

    top_transitions = [
            {"trigger": "TopGoDormant", "source": "EverythingOff", "dest": "Dormant"},
            {"trigger": "TopWakeUp", "source": "Dormant", "dest": "EverythingOff"},
    ]   

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        if self.settings.system_mode != SystemMode.Standby:
            raise Exception(
                f"Expect system mode Standby, got {self.settings.system_mode}"
            )
        self._stop_requested: bool = False
        self.buffer_declared_ready = False
        self.full_buffer_energy: Optional[float] = None  # in kWh

        self.top_machine = Machine(
            model=self,
            states=StandbyLocalControl.top_states,
            transitions=StandbyLocalControl.top_transitions,
            initial=LocalControlStandbyTopState.EverythingOff,
            send_event=True,
            model_attribute="top_state"
        )
        self.top_state: LocalControlStandbyTopState = LocalControlStandbyTopState.EverythingOff
        self.set_command_tree(boss_node=self.normal_node)
        self.actuators_ready = False
        self.log("Starting Standby Local Control")

    def trigger_top_event(self, cause: LocalControlStandbyTopEvent) -> None:
        """
        Trigger top event. Set relays_initialized to False if top state
        is Dormant. Report state change.
        """
        now_ms = int(time.time() * 1000)
        orig_state = self.top_state
        if cause == LocalControlStandbyTopEvent.TopGoDormant:
            self.TopGoDormant()
        elif cause == LocalControlStandbyTopEvent.TopWakeUp:
            self.TopWakeUp()
        
        if self.top_state == LocalControlStandbyTopState.Dormant:
            self.relays_initialized = False

        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=LocalControlStandbyTopState.enum_name(),
                State=self.top_state,
                UnixMs=now_ms,
                Cause=cause.value,
            ),
        )
        self.log(f"{cause}: {orig_state} -> {self.top_state}")
        self.log("Set top state command tree")

    @property
    def normal_node(self) -> ShNode:
        n = self.layout.node(H0N.local_control_normal)
        if n is None:
            raise Exception(f"{H0N.local_control_normal} is known to exist")
        return n

    def initialize_actuators(self) -> None:
        if not self.actuators_ready:
            self.log("Waiting to initialize actuators until actuator drivers are ready")
            return
        if self.top_state != LocalControlStandbyTopState.EverythingOff:
            raise Exception("Can not go into update_relays if top state is not EverythingOff")
        
        self.log("Initializing relays")
        h_normal_relays =  {
            relay
            for relay in self.my_actuators()
            if relay.ActorClass == ActorClass.Relay and
            self.the_boss_of(relay) == self.normal_node
        }

        relays_to_energize = {
            self.hp_failsafe_relay,
            self.hp_scada_ops_relay, 
            self.aquastat_control_relay,
            self.hp_loop_on_off,
        }

        target_relays: List[ShNode] = list(h_normal_relays - relays_to_energize)
        target_relays.sort(key=lambda x: x.Name)
        self.log("de-energizing most relays")
        for relay in target_relays:
            self.de_energize(relay, from_node=self.normal_node)

        self.log("energizing key relays for keeping things off")
        for relay in relays_to_energize:
            self.energize(relay, from_node=self.normal_node)
        
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
            self.log("Not processing message from message.Header.Src - no Node!")
            return Ok(True)
        match message.Payload:
            case ActuatorsReady():
                self.process_actuators_ready(from_node, message.Payload)
            case GoDormant():
                if len(self.my_actuators()) > 0:
                    raise Exception("LocalControl sent GoDormant with live actuators under it!")
                if self.top_state != LocalControlStandbyTopState.Dormant:
                    # TopGoDormant: Normal/UsingNonElectricBackup -> Dormant
                    self.trigger_top_event(cause=LocalControlStandbyTopEvent.TopGoDormant)
            case WakeUp():
                try:
                    self.process_wake_up(from_node, message.Payload)
                except Exception as e:
                    self.log(f"Trouble with process_wake_up: {e}")
            case HeatingForecast():
                ... # Ignore this

        return Ok(True)
    
    def process_actuators_ready(self, from_node: ShNode, payload: ActuatorsReady) -> None:
        """Initialize actuators if that hasn't happened yet"""
        if not self.actuators_ready:
            self.actuators_ready = True
            self.initialize_actuators()

    def process_wake_up(self, from_node: ShNode, payload: WakeUp) -> None:
        if self.top_state != LocalControlStandbyTopState.Dormant:
            return
        # TopWakeUp: Dormant -> EverythingOff
        self.trigger_top_event(LocalControlStandbyTopEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.normal_node)
        # Set actuators the way they need to be
        self.log("TopWakeUp: Dormant -> EverythingOff")
        self.initialize_actuators()

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)
            self.log(f"HaStrategy: Standby |  State: {self.top_state}")