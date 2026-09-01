"""NolanLocalControl — the Nolan layout family's local control.

The Nolan plant (radiant floors + fan coils, cooling, one store tank)
shares no control scheme with House0 tank storage. Normal runs TOU
cooling: the heat pump serves the house off-peak (weekends fully ON;
weekday on-peak windows OFF), with the ON transition sequenced iso valve
open → secondary pump on → cool call closed and the OFF transition cool
call open → pump off (the iso valve stays open; the DAC writer holds the
pump speed setting autonomously). Held zone circuits belong to the scada
with no call — deliberately latched, so a service stop cannot release
them. All commands are state-machine events in each actuator's own
vocabulary (change.valve.state, change.relay.state,
change.zone.call.source); the loop commands posture CHANGES, and the
relay layer's assert-then-verify is the standing enforcement underneath.
In Monitor it commands NOTHING — beside latched holds it inherits them
via relay boot-adoption and must not disturb them.

The plant nodes Normal requires are forced to exist by gw.nolan.layout
axiom 3 (LocalControlPlant). The schedule, the held-circuit set, and
mode-blindness carry design OFIs: operational params and a
gw1.service.mode Cooling gate.
"""

import asyncio
import time
from datetime import datetime
from datetime import time as dtime
from typing import Optional, Sequence

import pytz
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from result import Ok, Result
from transitions import Machine

from actors.hydronic.nolan import NolanHydronic
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeRelayState,
    ChangeValveState,
    ChangeZoneCallSource,
    LocalControlTopEvent,
    LocalControlTopState,
)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)
from gwsproto.names.nolan.node_names import NolanNodeNames
from gwsproto.named_types import (
    ActuatorsReady,
    GoDormant,
    HeatingForecast,
    SingleMachineState,
    WakeUp,
    ZoneCallCircuit,
)
from scada_app_interface import ScadaAppInterface


class NolanLocalControl(NolanHydronic):
    MAIN_LOOP_SLEEP_SECONDS = 300

    STARTUP_DELAY_S = 30.0
    # posture-change re-check cadence; the relay layer enforces in between
    TOU_CHECK_S = 60.0
    # pacing between actuations within a transition sequence
    SEQUENCE_STEP_S = 15.0

    # The nodes Normal requires. gw.nolan.layout axiom 3
    # (LocalControlPlant) forces them to exist at decode; construction
    # double-checks and crashes on a miss — never degrades.
    REQUIRED_NODES = (
        NolanNodeNames.iso_valve_relay,
        NolanNodeNames.secondary_pump_relay,
        HSNN.hp_scada_ops_relay,
    )

    # TOU cooling: weekday on-peak windows the HP is OFF; weekends fully
    # ON. Held circuits by board position. (OFI: operational params.)
    ONPEAK_WINDOWS = ((dtime(7, 0), dtime(12, 0)), (dtime(16, 0), dtime(20, 0)))
    HELD_CIRCUIT_POSITIONS = (1, 2, 4)

    # Normal runs control (the TOU loop); Monitor watches and commands
    # nothing; Dormant means admin holds the tree.
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
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.check_required_nodes(self.REQUIRED_NODES)
        self._held_circuit_relays: list[tuple[ZoneCallCircuit, ShNode, ShNode]] = [
            (
                c,
                self.required_node(c.FailsafeRelayNode),
                self.required_node(c.OpsRelayNode),
            )
            for c in (self.layout.hydronic.ZoneCallCircuits or [])
            if c.CircuitPosition in self.HELD_CIRCUIT_POSITIONS
        ]
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
            "Starting Nolan Local Control in Normal (TOU cooling; ops "
            f"ActuationAuthority {self.ops.ActuationAuthority}, ServiceMode {self.ops.ServiceMode})"
        )

    @property
    def normal_node(self) -> ShNode:
        n = self.layout.node(CoreNodeNames.local_control_normal)
        if n is None:
            raise Exception(
                f"{CoreNodeNames.local_control_normal} is known to exist"
            )
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
        latched hold stays a hold); the TOU loop establishes its own
        posture explicitly. Nothing to initialize."""
        self.log(
            "Nolan: actuators left at their adopted states; nothing commanded"
        )

    # ---- TOU cooling (Normal's behavior) ----

    def hp_should_be_on(self, now: datetime) -> bool:
        """TOU cooling schedule: weekends ON; weekdays ON except the
        on-peak windows."""
        if now.weekday() >= 5:
            return True
        t = dtime(now.hour, now.minute)
        return not any(
            start <= t < end for start, end in self.ONPEAK_WINDOWS
        )

    def command_zone_holds(self) -> None:
        """Held circuits belong to the scada with no call: failsafe
        SwitchToScada, ops OpenRelay — latched by design, so a service
        stop cannot release them."""
        for circuit, failsafe, ops in self._held_circuit_relays:
            self.send_state_command(
                failsafe,
                ChangeZoneCallSource.SwitchToScada.value,
                from_node=self.normal_node,
            )
            self.send_state_command(
                ops, ChangeRelayState.OpenRelay.value, from_node=self.normal_node
            )
            self.log(
                f"zone hold commanded: circuit {circuit.ServesZone} "
                f"(Z{circuit.CircuitPosition})"
            )

    async def command_sequence(
        self, steps: Sequence[tuple[ShNode, str]]
    ) -> None:
        """Issue state commands in order, paced so each actuation lands
        before the next."""
        for i, (node, event_name) in enumerate(steps):
            self.send_state_command(
                node, event_name, from_node=self.normal_node
            )
            if i < len(steps) - 1:
                await asyncio.sleep(self.SEQUENCE_STEP_S)

    async def turn_on_hp(self) -> None:
        """ON: iso valve open → secondary pump on → cool call closed."""
        await self.command_sequence(
            [
                (self.layout.iso_valve, ChangeValveState.OpenValve.value),
                (self.layout.secondary_pump_relay, ChangeRelayState.CloseRelay.value),
                (self.layout.hp_scada_ops_relay, ChangeRelayState.CloseRelay.value),
            ]
        )

    async def turn_off_hp(self) -> None:
        """OFF: cool call open → secondary pump off. The iso valve stays
        open; the DAC writer holds the pump speed setting."""
        await self.command_sequence(
            [
                (self.layout.hp_scada_ops_relay, ChangeRelayState.OpenRelay.value),
                (self.layout.secondary_pump_relay, ChangeRelayState.OpenRelay.value),
            ]
        )

    async def tou_control(self) -> None:
        """Normal's control loop: command the zone holds at (re-)entry,
        then hold the scheduled posture, re-commanding only on change —
        the relay layer's assert-then-verify enforces in between. The
        plant nodes are resolved at construction; the layout contract
        (gw.nolan.layout axiom 3) guarantees them."""
        await asyncio.sleep(self.STARTUP_DELAY_S)
        applied: Optional[bool] = None
        while not self._stop_requested:
            if self.top_state != LocalControlTopState.Normal:
                applied = None  # re-establish posture on re-entry
            else:
                if applied is None:
                    self.command_zone_holds()
                want_on = self.hp_should_be_on(datetime.now(self.timezone))
                if want_on != applied:
                    if want_on:
                        await self.turn_on_hp()
                    else:
                        await self.turn_off_hp()
                    applied = want_on
            await asyncio.sleep(self.TOU_CHECK_S)

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
            asyncio.create_task(self.main(), name="NolanLocalControl keepalive")
        )
        self.services.add_task(
            asyncio.create_task(
                self.tou_control(), name="NolanLocalControl tou"
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
