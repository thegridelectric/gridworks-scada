"""The standby machine, one for every layout family: the scada holds the
plant in the ops word's standby posture and runs no control loop. Having
claimed the standby node's tree, it de-energizes every relay directly under
that node except the ops word's EnergizedStandbyRelays, energizes those,
and tells hp-boss to turn the heat pump off (hp-boss has no dormant or
wake handling, so an admin session can leave it HpOn). The 0-10V outputs
stay at their power-on levels and are never written. The command tree
keeps its shape: five-v-boss runs, the sieg loop holds HoldFullSend,
hp-boss sits at HpOff. Standby refuses dispatch by axiom.

The top machine has two states. Standby holds the tree under the standby
node; Dormant means another node holds it. The posture is set at
ActuatorsReady and on each WakeUp that finds the machine Dormant."""

import asyncio
import time
from typing import Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from result import Ok, Result
from transitions import Machine

from actors.hydronic.shared import HydronicNode
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass, LocalControlTopEvent, LocalControlTopState
from gwsproto.named_types import ActuatorsReady, GoDormant, HeatingForecast, SingleMachineState, WakeUp
from scada_app_interface import ScadaAppInterface


class StandbyLocalControl(HydronicNode):
    MAIN_LOOP_SLEEP_SECONDS = 300

    top_states = [
        LocalControlTopState.Standby,
        LocalControlTopState.Dormant,
    ]
    top_transitions = [
        {
            "trigger": LocalControlTopEvent.TopGoDormant,
            "source": LocalControlTopState.Standby,
            "dest": LocalControlTopState.Dormant,
        },
        {
            "trigger": LocalControlTopEvent.TopWakeUp,
            "source": LocalControlTopState.Dormant,
            "dest": LocalControlTopState.Standby,
        },
    ]

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        if not self.ops.Standby:
            raise Exception("The standby machine runs only when the ops word says Standby")
        self._stop_requested: bool = False
        self.top_machine = Machine(
            model=self,
            states=StandbyLocalControl.top_states,
            transitions=StandbyLocalControl.top_transitions,
            initial=LocalControlTopState.Standby,
            send_event=True,
            model_attribute="top_state",
        )
        self.top_state: LocalControlTopState = LocalControlTopState.Standby
        self.set_command_tree(boss_node=self.standby_node)
        self.actuators_ready = False
        self.log(f"Starting standby local control, posture {self.ops.StandbyPosture}")

    @property
    def standby_node(self) -> ShNode:
        return self.layout.local_control_standby_node

    def trigger_top_event(self, cause: LocalControlTopEvent) -> None:
        orig_state = self.top_state
        getattr(self, cause.value)()
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=LocalControlTopState.enum_name(),
                State=self.top_state,
                UnixMs=int(time.time() * 1000),
                Cause=cause.value,
            ),
        )
        self.log(f"{cause}: {orig_state} -> {self.top_state}")

    def set_standby_posture(self) -> None:
        """The posture, in three steps: de-energize every relay directly
        under the standby node that the ops word does not list, energize the
        listed ones, tell hp-boss to turn the heat pump off."""
        if not self.actuators_ready:
            self.log("Waiting to set the standby posture until actuator drivers are ready")
            return
        energized = set(self.ops.EnergizedStandbyRelays)
        claimed = sorted(
            (
                relay
                for relay in self.my_actuators()
                if relay.ActorClass == ActorClass.Relay
                and self.the_boss_of(relay) == self.standby_node
            ),
            key=lambda relay: relay.Name,
        )
        for relay in claimed:
            if relay.Name not in energized:
                self.de_energize(relay, from_node=self.standby_node)
        for relay in claimed:
            if relay.Name in energized:
                self.energize(relay, from_node=self.standby_node)
        self.turn_off_hp(from_node=self.standby_node)
        self.log(
            f"Standby posture set: {len(claimed)} relays under {self.standby_node.handle}, "
            f"energized {sorted(energized)}, hp-boss told TurnOff"
        )

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
            self.log("Not processing message from message.Header.Src - no Node!")
            return Ok(True)
        match message.Payload:
            case ActuatorsReady():
                self.process_actuators_ready(from_node, message.Payload)
            case GoDormant():
                self.go_dormant()
            case WakeUp():
                try:
                    self.wake_up()
                except Exception as e:
                    self.log(f"Trouble with wake_up: {e}")
            case HeatingForecast():
                ...  # standby runs no loop that would use it
        return Ok(True)

    def process_actuators_ready(self, from_node: ShNode, payload: ActuatorsReady) -> None:
        if not self.actuators_ready:
            self.actuators_ready = True
            self.set_standby_posture()

    def go_dormant(self) -> None:
        if len(self.my_actuators()) > 0:
            raise Exception("LocalControl sent GoDormant with live actuators under it!")
        if self.top_state != LocalControlTopState.Dormant:
            self.trigger_top_event(LocalControlTopEvent.TopGoDormant)

    def wake_up(self) -> None:
        if self.top_state != LocalControlTopState.Dormant:
            return
        self.trigger_top_event(LocalControlTopEvent.TopWakeUp)
        self.set_command_tree(boss_node=self.standby_node)
        self.set_standby_posture()

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)
            self.log(f"Standby | State: {self.top_state}")
