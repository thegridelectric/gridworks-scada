import asyncio
from enum import auto
from typing import List, Optional, Sequence
import time
from actors.scada_interface import ScadaInterface
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import HomeAloneStrategy
from gw.enums import GwStrEnum
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from gwproto.enums import ActorClass
from gwproto import Message
from result import Ok, Result
from gwsproto.named_types import SingleMachineState
from gwproto.data_classes.sh_node import ShNode
from transitions import Machine
from actors.scada_actor import ScadaActor
from gwsproto.named_types import ActuatorsReady, GoDormant, HeatingForecast, WakeUp
from scada_app_interface import ScadaAppInterface


class SummerTopState(GwStrEnum):
    EverythingOff = auto()
    Dormant = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "summer.top.state"

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]


class SummerTopEvent(GwStrEnum):
    TopGoDormant = auto()
    TopWakeUp = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "summer.top.event"


class SummerHomeAlone(ScadaActor):
    MAIN_LOOP_SLEEP_SECONDS = 300
    top_states = SummerTopState.values()

    top_transitions = [
            {"trigger": "TopGoDormant", "source": "EverythingOff", "dest": "Dormant"},
            {"trigger": "TopWakeUp", "source": "Dormant", "dest": "EverythingOff"},
    ]   

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.strategy = HomeAloneStrategy(getattr(self.node, "Strategy", None))
        if self.strategy != HomeAloneStrategy.Summer:
            raise Exception(
                f"Expect ShoulderTou Summer, got {self.strategy}"
            )
        self._stop_requested: bool = False
        self.buffer_declared_ready = False
        self.full_buffer_energy: Optional[float] = None  # in kWh

        self.top_machine = Machine(
            model=self,
            states=SummerHomeAlone.top_states,
            transitions=SummerHomeAlone.top_transitions,
            initial=SummerTopState.EverythingOff,
            send_event=True,
            model_attribute="top_state"
        )
        self.top_state: SummerTopState = SummerTopState.EverythingOff
        self.set_command_tree(boss_node=self.normal_node)
        self.actuators_ready = False
        self.log("Starting Summer Home Alone")

    def trigger_top_event(self, cause: SummerTopEvent) -> None:
        """
        Trigger top event. Set relays_initialized to False if top state
        is Dormant. Report state change.
        """
        now_ms = int(time.time() * 1000)
        orig_state = self.top_state
        if cause == SummerTopEvent.TopGoDormant:
            self.TopGoDormant()
        elif cause == SummerTopEvent.TopWakeUp:
            self.TopWakeUp()
        
        if self.top_state == SummerTopState.Dormant:
            self.relays_initialized = False

        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=SummerTopState.enum_name(),
                State=self.top_state,
                UnixMs=now_ms,
                Cause=cause.value,
            ),
        )
        self.log(f"{cause}: {orig_state} -> {self.top_state}")
        self.log("Set top state command tree")

    @property
    def normal_node(self) -> ShNode:
        return self.layout.node(H0N.home_alone_normal)

    def initialize_actuators(self) -> None:
        if not self.actuators_ready:
            self.log(f"Waiting to initialize actuators until actuator drivers are ready")
            return
        if self.top_state != SummerTopState.EverythingOff:
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
                if self.top_state != SummerTopState.Dormant:
                    # TopGoDormant: Normal/UsingBackup -> Dormant
                    self.trigger_top_event(cause=SummerTopEvent.TopGoDormant)
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
        if self.top_state != SummerTopState.Dormant:
            return
        # TopWakeUp: Dormant -> EverythingOff
        self.trigger_top_event(SummerTopEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.normal_node)
        # Set actuators the way they need to be
        self.log(f"TopWakeUp: Dormant -> EverythingOff")
        self.initialize_actuators()

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)
            self.log(f"HaStrategy: Summer  |  State: {self.top_state}")