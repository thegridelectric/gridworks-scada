"""sieg-loop, the Siegenthaler-loop actor: one valve, driven by the
strategy the ops word selects. The facade owns what every strategy shares,
the valve and its state report, the command surface, the tick, the
watchdog pat and the hp-boss subscription; the strategy decides what the
valve does under automatic control."""

import asyncio
import time
from typing import Any, Optional, Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.message import Message
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import TelemetryName, Unit
from gwsproto.enums import (
    FsmReportType,
    HpBossState,
    MoveSiegValve,
    ScadaCmdRefusalReason,
    SiegLoopStrategy,
    SiegValveState,
)
from gwsproto.named_types import (
    ActuatorsReady,
    FsmAtomicReport,
    FsmEvent,
    FsmFullReport,
    SingleMachineState,
)
from gwsproto.names.house0.channel_names import House0ChannelNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from result import Ok, Result

from actors import command_reply
from actors.hydronic.house0 import House0Hydronic
from actors.sieg_loop.hold_full_send import HoldFullSend
from actors.sieg_loop.strat_protect import SiegControlEvent, SiegControlState, StratProtect
from actors.sieg_loop.strategy import SiegLoopReady, SiegStrategy, selected_strategy
from actors.sieg_loop.valve import SiegValve, SiegValveEvent
from scada_app_interface import ScadaAppInterface

__all__ = [
    "HoldFullSend",
    "SiegControlEvent",
    "SiegControlState",
    "SiegLoop",
    "SiegLoopReady",
    "SiegStrategy",
    "SiegValve",
    "SiegValveEvent",
    "SiegValveState",
    "StratProtect",
    "selected_strategy",
]


# The loop's neighbourhood: the channels the sieg-view strip carries when
# the layout names them. Debug output for the maple test-drives; removed
# with the strip once they are done.
VIEW_CHANNELS: tuple[str, ...] = (
    HCN.hp_lwt,
    HCN.hp_ewt,
    House0ChannelNames.sieg_hot,
    House0ChannelNames.sieg_cold,
    House0ChannelNames.sieg_flow,
    House0ChannelNames.sieg_send_flow,
    HCN.primary_flow,
    HCN.hp_odu_pwr,
    HCN.hp_idu_pwr,
    HCN.buffer_hot_pipe,
    HCN.buffer_cold_pipe,
    HCN.store_hot_pipe,
    HCN.dist_swt,
    HCN.dist_rwt,
)
FLOW_UNITS = {TelemetryName.GpmTimes100, Unit.GpmX100}
POWER_UNITS = {TelemetryName.PowerW, Unit.Watts}


def boss_of(handle: str) -> str:
    """The handle with its last segment removed: whose tree the node sits in."""
    return ".".join(handle.split(".")[:-1])


class SiegLoop(House0Hydronic):
    """Base class: House0Hydronic carries the relay choreography for relays
    14 and 15 (change_to_hp_keep_more / _less, sieg_valve_active / _hold)
    and the loop's reads (lwt, ewt, lift_f, total_hp_pwr_w). A fall-2026
    layout has a Siegenthaler loop without the House0 hydronic set, so the
    choreography is not House0's; the base class changes with that layout.

    A command from the boss (MoveSiegValve) takes the loop out of automatic
    control: the strategy's moves are withheld until the tree changes hands,
    noticed on the tick, when the strategy resumes. The move a command asks
    for is a full run, so a command to the stop the valve is already on
    re-homes it.
    """

    CONTROL_INTERVAL_S = 30
    PAT_INTERVAL_S = 5 * 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self.stop_requested = False
        self.actuators_ready = False
        self.since_last_pat_s = self.PAT_INTERVAL_S
        self.valve = SiegValve(self)
        # The boss whose command holds the loop, None under automatic control.
        self.commanded_by: Optional[str] = None
        # The command in flight: its TriggerId, its event and the valve
        # state it started from, for the full report when the move ends.
        self.trigger_id: Optional[str] = None
        self.command_event: Optional[MoveSiegValve] = None
        self.command_from_state: Optional[SiegValveState] = None
        strategy = selected_strategy(self.ops)
        if strategy is SiegLoopStrategy.HoldFullSend:
            self.strategy: SiegStrategy = HoldFullSend(self)
        elif strategy is SiegLoopStrategy.StratProtect:
            self.strategy = StratProtect(self)
        else:
            raise ValueError(
                f"{self.name} cannot run SiegLoopStrategy {strategy}: only "
                f"{SiegLoopStrategy.HoldFullSend} and {SiegLoopStrategy.StratProtect} are built"
            )
        self.log(f"Running {type(self.strategy).__name__}")

    @property
    def automatic(self) -> bool:
        return self.commanded_by is None

    # --------------------------------------
    # Main loop
    # --------------------------------------

    async def main(self) -> None:
        while not self.stop_requested:
            self.tick()
            await self.services.clock.sleep(self.CONTROL_INTERVAL_S)

    def tick(self) -> None:
        if self.commanded_by is not None and boss_of(self.node.handle) != self.commanded_by:
            self.log(f"Tree left {self.commanded_by}: back under automatic control")
            self.commanded_by = None
            self.strategy.resume()
        self.strategy.tick()
        self.log_view()
        if self.since_last_pat_s >= self.PAT_INTERVAL_S:
            self.since_last_pat_s = 0
            self._send(PatInternalWatchdogMessage(src=self.name))
        self.since_last_pat_s += self.CONTROL_INTERVAL_S

    # --------------------------------------
    # Message processing
    # --------------------------------------

    def process_message(self, message: Message[Any]) -> Result[bool, Exception]:
        from_node = self.layout.node(message.Header.Src, None)
        if from_node is None:
            return Ok(False)
        payload = message.Payload
        match payload:
            case ActuatorsReady():
                self.actuators_ready = True
                self.strategy.on_actuators_ready()
            case SingleMachineState():
                self.process_single_machine_state(from_node, payload)
            case FsmEvent():
                self.process_fsm_event(from_node, payload)
            case _:
                self.log(f"{self.name} received unexpected message: {message.Header}")
        return Ok(True)

    def process_single_machine_state(self, from_node: ShNode, payload: SingleMachineState) -> None:
        if payload.StateEnum != HpBossState.enum_name():
            raise Exception(
                f"The StateEnum {payload.StateEnum} is not a HpBossState enum: {HpBossState.enum_name()}"
            )
        if from_node != self.hp_boss:
            raise Exception("Not expecting single machine state messages except from HpBoss")
        self.log(f"Just received state {payload.State} from HpBoss")
        self.strategy.on_hp_boss_state(HpBossState(payload.State))

    # --------------------------------------
    # Commands from the boss
    # --------------------------------------

    def process_fsm_event(self, from_node: ShNode, payload: FsmEvent) -> None:
        if payload.FromHandle != from_node.handle:
            self.send_warning(
                "bad_sender",
                f"{from_node.name} (handle {from_node.handle}) sent a command claiming "
                f"FromHandle {payload.FromHandle}. Ignoring!",
            )
            return
        if payload.ToHandle != self.node.handle:
            self.log(f"Handle is {self.node.handle}; refusing {payload.FromHandle} -> {payload.ToHandle}")
            self.refuse(from_node, payload, ScadaCmdRefusalReason.NotMyBoss)
            return
        if payload.EventType != MoveSiegValve.enum_name() or payload.EventName not in MoveSiegValve.values():
            self.log(f"Takes {MoveSiegValve.enum_name()}; refusing {payload.EventType} {payload.EventName}")
            self.refuse(from_node, payload, ScadaCmdRefusalReason.UnknownEvent)
            return
        self._send_to(
            from_node,
            command_reply.ack(self.node.handle, payload.FromHandle, payload.TriggerId),
        )
        event = MoveSiegValve(payload.EventName)
        self.commanded_by = boss_of(self.node.handle)
        self.trigger_id = payload.TriggerId
        self.command_event = event
        self.command_from_state = self.valve.valve_state
        self.log(f"{event} from {payload.FromHandle}: the loop is held until the tree changes hands")
        if event == MoveSiegValve.MoveToFullSend:
            self.valve.full_run_to_send()
        else:
            self.valve.full_run_to_keep()

    def refuse(self, from_node: ShNode, payload: FsmEvent, reason: ScadaCmdRefusalReason) -> None:
        self._send_to(
            from_node,
            command_reply.nack(self.node.handle, payload.FromHandle, payload.TriggerId, reason),
        )

    # --------------------------------------
    # Reporting
    # --------------------------------------

    def report_valve_state(self, cause: SiegValveEvent) -> None:
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=SiegValveState.enum_name(),
                State=self.valve.valve_state,
                UnixMs=self.services.clock.now_ms(),
                Cause=cause,
            ),
        )
        self.log_view()

    # --------------------------------------
    # The sieg-view strip (debug output for the maple test-drives)
    # --------------------------------------

    def view_value(self, name: str, raw: int) -> str:
        """The channel's latest raw value in the house's units."""
        unit = self.layout.channel_registry.unit(name)
        if unit in FLOW_UNITS:
            return f"{raw / 100:.2f}gpm"
        if unit in POWER_UNITS:
            return f"{raw}W"
        return f"{self.layout.channel_registry.temperature(name, raw).f:.1f}F"

    def view(self) -> str:
        """One line: every channel of VIEW_CHANNELS the layout names, with
        its latest value or `--` when there is none, the reading's age in
        seconds, and `*` on a derived channel; then the quantities the
        strategy acts on, lift and total power, and the blind reason when
        the strategy is blind."""
        now_s = time.time()
        parts: list[str] = []
        for name in VIEW_CHANNELS:
            channel = self.layout.channel_registry.get(name)
            if channel is None:
                continue
            label = f"{name}*" if isinstance(channel, DerivedChannel) else name
            raw = self.data.latest_channel_values.get(name)
            unix_ms = self.data.latest_channel_unix_ms.get(name)
            if raw is None or unix_ms is None:
                parts.append(f"{label}=--")
            else:
                parts.append(f"{label}={self.view_value(name, raw)}@{now_s - unix_ms / 1000:.0f}s")
        lift = self.lift_f()
        pwr = self.total_hp_pwr_w()
        tail = [
            f"lift={'--' if lift is None else f'{lift:.1f}F'}",
            f"pwr={'--' if pwr is None else f'{pwr:.0f}W'}",
        ]
        reason = self.strategy.blind_reason()
        if reason is not None:
            tail.append(f"blind={reason}")
        return f"sieg-view {self.valve.valve_state} " + " ".join(parts) + " | " + " ".join(tail)

    def log_view(self) -> None:
        self.log(self.view())

    def move_ended(self) -> None:
        """The motor stopped. A commanded move reports in full under the
        commander's TriggerId; an automatic one has nothing to add to the
        valve state already reported."""
        if self.trigger_id is None or self.command_event is None or self.command_from_state is None:
            return
        self._send_to(
            self.primary_scada,
            FsmFullReport(
                FromName=self.name,
                TriggerId=self.trigger_id,
                AtomicList=[
                    FsmAtomicReport(
                        MachineHandle=self.node.handle,
                        StateEnum=SiegValveState.enum_name(),
                        ReportType=FsmReportType.Event,
                        EventEnum=MoveSiegValve.enum_name(),
                        Event=self.command_event,
                        FromState=self.command_from_state,
                        ToState=self.valve.valve_state,
                        UnixTimeMs=self.services.clock.now_ms(),
                        TriggerId=self.trigger_id,
                    )
                ],
            ),
        )
        self.trigger_id = None
        self.command_event = None
        self.command_from_state = None

    # --------------------------------------
    # Required methods and properties
    # --------------------------------------

    def start(self) -> None:
        self.services.add_task(asyncio.create_task(self.main(), name="Sieg Loop Synchronous Report"))

    def stop(self) -> None:
        self.stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, 400)]
