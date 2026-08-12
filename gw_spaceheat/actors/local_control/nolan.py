"""NolanLocalControl — the Nolan layout family's local control.

The Nolan plant (radiant floors + fan coils, cooling, one store tank) shares
no control scheme with House0 tank storage, so this implementation starts
from the witness end: it boots into Normal, runs the scripted spruce-window
experiment sequence (fancoil takeover + call, secondary pump start/stop —
the system-working EDD harness's first two experiments), then segues to
Monitor and just watches. In Monitor it commands NOTHING — deployed beside
latched summer holds it inherits them via relay boot-adoption and must not
disturb them. The TOU schedule and zone circuit governance land here
incrementally, replacing the scripted witness as Normal's behavior.
"""

import asyncio
import time
from typing import Callable, Optional, Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from result import Ok, Result
from transitions import Machine

from actors.sh_node_actor import ShNodeActor
from gwsproto.data_classes.components import I2cRelayComponent
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    LocalControlTopEvent,
    LocalControlTopState,
    ZoneActuatorKind,
)
from gwsproto.named_types import (
    ActuatorsReady,
    GoDormant,
    HeatingForecast,
    SingleMachineState,
    WakeUp,
    ZoneCallCircuit,
)
from scada_app_interface import ScadaAppInterface


class NolanLocalControl(ShNodeActor):
    MAIN_LOOP_SLEEP_SECONDS = 300

    # Scripted-witness pacing. The call hold spans the Caleffi zone-control
    # box's latency (seconds to ~half a minute between our relay and a
    # visible distribution response) plus observation time.
    STARTUP_DELAY_S = 30.0
    STEP_S = 15.0
    CALL_HOLD_S = 90.0
    PUMP_HOLD_S = 60.0

    # The secondary pump's board-record RelayName (gw1.scada.device.type.gt
    # I2cRelays vocabulary).
    SECONDARY_PUMP_RELAY_NAME = "SecondaryPump"

    # Normal runs control (today: the scripted witness); Monitor watches and
    # commands nothing; Dormant means admin holds the tree.
    top_states = LocalControlTopState.values()
    top_transitions = [
        {"trigger": "MonitorOnly", "source": "Normal", "dest": "Monitor"},
        {"trigger": "MonitorAndControl", "source": "Monitor", "dest": "Normal"},
        {"trigger": "TopGoDormant", "source": "Normal", "dest": "Dormant"},
        {"trigger": "TopGoDormant", "source": "Monitor", "dest": "Dormant"},
        {"trigger": "TopWakeUp", "source": "Dormant", "dest": "Monitor"},
    ]

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._stop_requested: bool = False
        self.actuators_ready = False
        self.top_machine = Machine(
            model=self,
            states=NolanLocalControl.top_states,
            transitions=NolanLocalControl.top_transitions,
            initial=LocalControlTopState.Normal,
            send_event=True,
            model_attribute="top_state",
        )
        self.top_state: LocalControlTopState = LocalControlTopState.Normal
        self.set_command_tree(boss_node=self.normal_node)
        self.log(
            "Starting Nolan Local Control in Normal (scripted witness; ops "
            f"SystemMode {self.ops.SystemMode})"
        )

    @property
    def normal_node(self) -> ShNode:
        n = self.layout.node(H0N.local_control_normal)
        if n is None:
            raise Exception(f"{H0N.local_control_normal} is known to exist")
        return n

    def trigger_top_event(self, cause: LocalControlTopEvent) -> None:
        now_ms = int(time.time() * 1000)
        orig_state = self.top_state
        if cause == LocalControlTopEvent.TopGoDormant:
            self.TopGoDormant()
        elif cause == LocalControlTopEvent.TopWakeUp:
            self.TopWakeUp()
        elif cause == LocalControlTopEvent.MonitorOnly:
            self.MonitorOnly()
        elif cause == LocalControlTopEvent.MonitorAndControl:
            self.MonitorAndControl()
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
        self.log(f"{cause}: {orig_state} -> {self.top_state}")

    def initialize_actuators(self) -> None:
        """The actuators keep the states they adopted from the pins (a
        latched hold stays a hold); the scripted witness commands its own
        sequence explicitly. Nothing to initialize."""
        self.log(
            "Nolan: actuators left at their adopted states; nothing commanded"
        )

    # ---- the scripted witness (Normal's behavior, for now) ----

    def _fancoil_circuit(self) -> Optional[ZoneCallCircuit]:
        circuits = self.layout.hydronic.ZoneCallCircuits or []
        return next(
            (c for c in circuits if c.ActuatorKind == ZoneActuatorKind.Fancoil),
            None,
        )

    def _relay_node_by_board_name(self, relay_name: str) -> Optional[ShNode]:
        return next(
            (
                n
                for n in self.layout.nodes.values()
                if isinstance(n.component, I2cRelayComponent)
                and n.component.gt.RelayName == relay_name
            ),
            None,
        )

    async def _scripted_witness(self) -> None:
        """Take the fancoil circuit and make a call (the distribution
        response is the observable), release it; run the secondary pump
        (secondary-flow is the observable), stop it; segue to Monitor.
        Skips cleanly to Monitor on layouts without the target records."""
        await asyncio.sleep(self.STARTUP_DELAY_S)
        if self.top_state != LocalControlTopState.Normal:
            return
        circuit = self._fancoil_circuit()
        pump = self._relay_node_by_board_name(self.SECONDARY_PUMP_RELAY_NAME)
        failsafe = (
            self.layout.node(circuit.FailsafeRelayNode) if circuit else None
        )
        ops = self.layout.node(circuit.OpsRelayNode) if circuit else None
        if failsafe is None or ops is None or pump is None:
            self.log(
                "scripted witness: this layout lacks a fancoil circuit "
                "and/or a secondary-pump relay; going observe-only"
            )
            self.trigger_top_event(LocalControlTopEvent.MonitorOnly)
            return
        steps: list[tuple[str, Callable[..., None], ShNode, float]] = [
            ("fancoil takeover", self.energize, failsafe, self.STEP_S),
            ("fancoil call ON", self.energize, ops, self.CALL_HOLD_S),
            ("fancoil call OFF", self.de_energize, ops, self.STEP_S),
            ("fancoil release to stat", self.de_energize, failsafe, self.STEP_S),
            ("secondary pump ON", self.energize, pump, self.PUMP_HOLD_S),
            ("secondary pump OFF", self.de_energize, pump, self.STEP_S),
        ]
        for label, actuate, node, hold_s in steps:
            if self.top_state != LocalControlTopState.Normal:
                self.log(
                    f"scripted witness aborted before '{label}': top state "
                    f"{self.top_state}"
                )
                return
            self.log(f"scripted witness: {label}")
            actuate(node, from_node=self.normal_node)
            await asyncio.sleep(hold_s)
        self.log("scripted witness complete: segue to observe-only")
        if self.top_state == LocalControlTopState.Normal:
            self.trigger_top_event(LocalControlTopEvent.MonitorOnly)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            self.log("Not processing message from message.Header.Src - no Node!")
            return Ok(True)
        match message.Payload:
            case ActuatorsReady():
                if not self.actuators_ready:
                    self.actuators_ready = True
                    self.initialize_actuators()
            case GoDormant():
                if len(self.my_actuators()) > 0:
                    raise Exception(
                        "LocalControl sent GoDormant with live actuators under it!"
                    )
                if self.top_state != LocalControlTopState.Dormant:
                    self.trigger_top_event(LocalControlTopEvent.TopGoDormant)
            case WakeUp():
                if self.top_state == LocalControlTopState.Dormant:
                    self.trigger_top_event(LocalControlTopEvent.TopWakeUp)
                    self.set_command_tree(boss_node=self.normal_node)
                    self.initialize_actuators()
            case HeatingForecast():
                ...  # a Nolan house has no House0 heating-forecast consumer yet
        return Ok(True)

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name="NolanLocalControl keepalive")
        )
        self.services.add_task(
            asyncio.create_task(
                self._scripted_witness(), name="NolanLocalControl witness"
            )
        )

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self):
        ...

    def init(self) -> None:
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)
