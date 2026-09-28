"""The Siegenthaler valve: the only code that addresses relays 14 (motor
on/off) and 15 (keep/send direction). Its position is kept as keep_seconds,
the motor time from full send toward full keep, and a move is one motor run
timed on the scada's clock."""

import asyncio
from dataclasses import dataclass, field
from enum import auto
from typing import TYPE_CHECKING, Optional

from gwsproto.enums import MoveSiegValve, SiegValveState
from gwsproto.enums.gw_str_enum import GwStrEnum
from gwsproto.named_types import FsmAtomicReport
from transitions import Machine

if TYPE_CHECKING:
    from actors.sieg_loop import SiegLoop


class SiegValveEvent(GwStrEnum):
    StartKeepingMore = auto()
    StartKeepingLess = auto()
    StopKeepingMore = auto()
    StopKeepingLess = auto()
    ResetToFullySend = auto()
    ResetToFullyKeep = auto()


@dataclass
class Move:
    """One motor run and its written record. trigger_id names it in every
    relay command and in the full report; event is the boss's command when
    the move was commanded, None when the strategy chose it; from_state is
    the valve state before the run; atomics collects the relays' reports as
    they arrive; pending holds, by relay name, the confirmation the loop is
    waiting for from each relay commanded in the current phase; started is
    set when the run picks the move up."""

    trigger_id: str
    from_state: SiegValveState
    event: Optional[MoveSiegValve] = None
    atomics: list[FsmAtomicReport] = field(default_factory=list)
    pending: dict[str, "asyncio.Future[bool]"] = field(default_factory=dict)
    started: bool = False


class SiegValve:
    """The valve state machine and its motor runs. A run toward keep adds
    to keep_seconds, a run toward send subtracts; both overshoot the range
    by ten seconds when the target is a stop. A run that ends on a stop
    lands the machine on FullySend or FullyKeep; any other end is
    SteadyBlend. A new run cancels the one in flight, which settles its
    keep_seconds from the clock before the motor changes direction. A
    full run is the whole range plus the overshoot whatever keep_seconds
    says, which is how a commanded move re-homes the valve. A stop cancels
    the run in flight without starting another: the run settles the same
    way and ends under the stop's move."""

    # Positions are motor seconds from the send stop. The flow split
    # changes only between keep onset (t1) and keep complete (t2); the
    # motor runs on to the keep stop beyond. Measured at maple from the
    # flow meters during full travels, 2026-09-28; the meters answered
    # about 4 s after the motor, and that lag is taken out of each. They
    # are facts about one valve and belong in the layout as parameters.
    FULL_RANGE_S = 94  # keep stop
    OVERSHOOT_S = 10

    transitions = [
        {"trigger": "StartKeepingMore", "source": "FullySend", "dest": "KeepingMore", "before": "before_keeping_more"},
        {"trigger": "StartKeepingMore", "source": "FullyKeep", "dest": "KeepingMore", "before": "before_keeping_more"},
        {"trigger": "StartKeepingMore", "source": "SteadyBlend", "dest": "KeepingMore", "before": "before_keeping_more"},
        {"trigger": "StartKeepingMore", "source": "KeepingLess", "dest": "KeepingMore", "before": "before_keeping_more"},
        {"trigger": "StartKeepingMore", "source": "KeepingMore", "dest": "KeepingMore", "before": "before_keeping_more"},

        {"trigger": "StartKeepingLess", "source": "FullyKeep", "dest": "KeepingLess", "before": "before_keeping_less"},
        {"trigger": "StartKeepingLess", "source": "FullySend", "dest": "KeepingLess", "before": "before_keeping_less"},
        {"trigger": "StartKeepingLess", "source": "SteadyBlend", "dest": "KeepingLess", "before": "before_keeping_less"},
        {"trigger": "StartKeepingLess", "source": "KeepingMore", "dest": "KeepingLess", "before": "before_keeping_less"},
        {"trigger": "StartKeepingLess", "source": "KeepingLess", "dest": "KeepingLess", "before": "before_keeping_less"},

        {"trigger": "StopKeepingMore", "source": "KeepingMore", "dest": "SteadyBlend", "before": "before_keeping_steady"},
        {"trigger": "StopKeepingLess", "source": "KeepingLess", "dest": "SteadyBlend", "before": "before_keeping_steady"},

        {"trigger": "ResetToFullySend", "source": "KeepingLess", "dest": "FullySend", "before": "before_keeping_steady"},
        {"trigger": "ResetToFullyKeep", "source": "KeepingMore", "dest": "FullyKeep", "before": "before_keeping_steady"},
    ]

    def __init__(self, loop: "SiegLoop") -> None:
        self.loop = loop
        self.machine = Machine(
            model=self,
            states=SiegValveState.values(),
            transitions=self.transitions,
            initial=SiegValveState.FullyKeep,
            model_attribute="valve_state",
            send_event=True,
        )
        self.valve_state: SiegValveState = SiegValveState.FullyKeep
        self.keep_seconds: float = self.FULL_RANGE_S
        self.t1 = 26  # keep onset: the keep opening appears
        self.t2 = 56  # keep complete: all flow is kept from here on
        self.task: Optional[asyncio.Task[None]] = None
        # The move the run in flight is making; None between runs.
        self.move: Optional[Move] = None
        # The commanded stop cancelling the run in flight; None when the run
        # ends by itself or is cancelled by the next run.
        self.stopping: Optional[Move] = None

    # --------------------------------------
    # Targets
    # --------------------------------------

    def move_to_full_send(self) -> None:
        self.loop.log("Moving to full send")
        self.travel(-self.keep_seconds - self.OVERSHOOT_S)

    def move_to_full_keep(self) -> None:
        self.loop.log("Moving to full keep")
        self.travel(-self.keep_seconds + self.FULL_RANGE_S + self.OVERSHOOT_S)

    def move_to_just_keep(self) -> None:
        self.loop.log("Moving to just keep")
        self.travel(-self.keep_seconds + self.t2)

    def full_run_to_send(self) -> None:
        self.loop.log("Full run to send")
        self.travel(-(self.FULL_RANGE_S + self.OVERSHOOT_S))

    def full_run_to_keep(self) -> None:
        self.loop.log("Full run to keep")
        self.travel(self.FULL_RANGE_S + self.OVERSHOOT_S)

    def stop(self, stop: Move) -> None:
        """Stop the motor where it is. With the motor running, the run in
        flight is cancelled and ends under the stop's move. With the motor
        at rest nothing moves and the stop reports the valve's state as it
        stands."""
        running = self.valve_state in (SiegValveState.KeepingMore, SiegValveState.KeepingLess)
        if self.task is None or self.task.done() or not running:
            self.loop.log(f"Motor at rest: {self.valve_state} at keep_seconds {round(self.keep_seconds, 1)}")
            self.loop.move_ended(stop, self.valve_state)
            return
        self.loop.log("Stopping the motor")
        self.stopping = stop
        self.task.cancel()

    def travel(self, delta_s: float) -> None:
        """Run the motor for delta_s seconds: toward keep when positive,
        toward send when negative. Cancels the run in flight."""
        if delta_s == 0:
            self.loop.log("Already at target")
            return
        self.task = asyncio.create_task(self.run(delta_s, self.task), name="sieg valve travel")

    async def run(self, delta_s: float, previous: Optional[asyncio.Task[None]]) -> None:
        """One move: the start transition commands the relays under the
        move's id, the motor clock starts once both relays have reported
        (or the loop's wait runs out), the stop transition opens the on/off
        relay, and the move ends with its full report. A nack from a relay
        skips the motor time. A run cancelled by the next move settles from
        the clock and reports without waiting on the hold. A run cancelled
        by a stop settles from the clock, commands the hold under the
        stop's TriggerId and waits on it; the run's move reports without
        the hold, then the stop's move reports with it."""
        if previous is not None and not previous.done():
            previous.cancel()
            await asyncio.wait([previous])
        clock = self.loop.services.clock
        toward_keep = delta_s > 0
        move = self.loop.begin_move(self.valve_state)
        self.move = move
        self.trigger_valve_event(
            SiegValveEvent.StartKeepingMore if toward_keep else SiegValveEvent.StartKeepingLess
        )
        start_keep_seconds = self.keep_seconds
        self.loop.log(
            f"Motor {'toward keep' if toward_keep else 'toward send'} for "
            f"{round(abs(delta_s), 1)} s from keep_seconds {round(start_keep_seconds, 1)}"
        )
        ran_s = 0.0
        cancelled = False
        try:
            if await self.loop.relays_reported(move):
                start_s = clock.now()
                try:
                    await clock.sleep(abs(delta_s))
                finally:
                    ran_s = clock.now() - start_s
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            stop = self.stopping
            self.stopping = None
            if stop is not None:
                self.move = stop
            moved = ran_s if toward_keep else -ran_s
            self.keep_seconds = min(self.FULL_RANGE_S, max(0, start_keep_seconds + moved))
            if toward_keep:
                at_stop = self.keep_seconds == self.FULL_RANGE_S
                self.trigger_valve_event(
                    SiegValveEvent.ResetToFullyKeep if at_stop else SiegValveEvent.StopKeepingMore
                )
            else:
                at_stop = self.keep_seconds == 0
                self.trigger_valve_event(
                    SiegValveEvent.ResetToFullySend if at_stop else SiegValveEvent.StopKeepingLess
                )
            self.loop.log(
                f"Motor stopped after {round(ran_s, 1)} s: keep_seconds {round(self.keep_seconds, 1)}"
            )
            if stop is not None:
                await self.loop.relays_reported(stop)
            elif not cancelled:
                await self.loop.relays_reported(move)
            self.move = None
            self.loop.move_ended(move, self.valve_state)
            if stop is not None:
                self.loop.move_ended(stop, self.valve_state)

    # --------------------------------------
    # Valve state machine
    # --------------------------------------

    def trigger_valve_event(self, event: SiegValveEvent) -> None:
        orig_state = self.valve_state
        getattr(self, event)(self)
        if self.valve_state == orig_state:
            self.loop.log(f"{event}: valve state stays {orig_state}")
            return
        self.loop.log(f"{event}: {orig_state} -> {self.valve_state}")
        self.loop.report_valve_state(event)

    def current_move(self) -> Move:
        """The move the transition belongs to: the run's, or a new one when
        the transition is fired outside a run."""
        if self.move is None:
            self.move = self.loop.begin_move(self.valve_state)
        return self.move

    def before_keeping_more(self, event: SiegValveEvent) -> None:
        move = self.current_move()
        self.loop.expect_reports(move, self.loop.layout.hp_loop_keep_send, self.loop.layout.hp_loop_on_off)
        self.loop.change_to_hp_keep_more(move.trigger_id)
        self.loop.sieg_valve_active(move.trigger_id)

    def before_keeping_less(self, event: SiegValveEvent) -> None:
        move = self.current_move()
        self.loop.expect_reports(move, self.loop.layout.hp_loop_keep_send, self.loop.layout.hp_loop_on_off)
        self.loop.change_to_hp_keep_less(move.trigger_id)
        self.loop.sieg_valve_active(move.trigger_id)

    def before_keeping_steady(self, event: SiegValveEvent) -> None:
        move = self.current_move()
        self.loop.expect_reports(move, self.loop.layout.hp_loop_on_off)
        self.loop.sieg_valve_hold(move.trigger_id)
