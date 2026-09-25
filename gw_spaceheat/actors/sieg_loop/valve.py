"""The Siegenthaler valve: the only code that addresses relays 14 (motor
on/off) and 15 (keep/send direction). Its position is kept as keep_seconds,
the motor time from full send toward full keep, and a move is one motor run
timed on the scada's clock."""

import asyncio
from enum import auto
from typing import TYPE_CHECKING, Optional

from gwsproto.enums.gw_str_enum import GwStrEnum
from transitions import Machine

if TYPE_CHECKING:
    from actors.sieg_loop import SiegLoop


class SiegValveState(GwStrEnum):
    KeepingMore = auto()
    KeepingLess = auto()
    SteadyBlend = auto()
    FullySend = auto()
    FullyKeep = auto()

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "sieg.valve.state"


class SiegValveEvent(GwStrEnum):
    StartKeepingMore = auto()
    StartKeepingLess = auto()
    StopKeepingMore = auto()
    StopKeepingLess = auto()
    ResetToFullySend = auto()
    ResetToFullyKeep = auto()


class SiegValve:
    """The valve state machine and its motor runs. A run toward keep adds
    to keep_seconds, a run toward send subtracts; both overshoot the range
    by ten seconds when the target is a stop, which is how the valve
    re-homes. A new run cancels the one in flight, which settles its
    keep_seconds from the clock before the motor changes direction."""

    FULL_RANGE_S = 100
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
        # Motor seconds from full send at which flow starts through the loop,
        # and at which all of it does.
        self.t1 = 26
        self.t2 = self.FULL_RANGE_S - 18
        self.task: Optional[asyncio.Task[None]] = None

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

    def travel(self, delta_s: float) -> None:
        """Run the motor for delta_s seconds: toward keep when positive,
        toward send when negative. Cancels the run in flight."""
        if delta_s == 0:
            self.loop.log("Already at target")
            return
        self.task = asyncio.create_task(self.run(delta_s, self.task), name="sieg valve travel")

    async def run(self, delta_s: float, previous: Optional[asyncio.Task[None]]) -> None:
        if previous is not None and not previous.done():
            previous.cancel()
            await asyncio.wait([previous])
        clock = self.loop.services.clock
        toward_keep = delta_s > 0
        self.trigger_valve_event(
            SiegValveEvent.StartKeepingMore if toward_keep else SiegValveEvent.StartKeepingLess
        )
        start_s = clock.now()
        start_keep_seconds = self.keep_seconds
        self.loop.log(
            f"Motor {'toward keep' if toward_keep else 'toward send'} for "
            f"{round(abs(delta_s), 1)} s from keep_seconds {round(start_keep_seconds, 1)}"
        )
        try:
            await clock.sleep(abs(delta_s))
        finally:
            ran_s = clock.now() - start_s
            moved = ran_s if toward_keep else -ran_s
            self.keep_seconds = min(self.FULL_RANGE_S, max(0, start_keep_seconds + moved))
            self.trigger_valve_event(
                SiegValveEvent.StopKeepingMore if toward_keep else SiegValveEvent.StopKeepingLess
            )
            self.loop.log(
                f"Motor stopped after {round(ran_s, 1)} s: keep_seconds {round(self.keep_seconds, 1)}"
            )

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

    def before_keeping_more(self, event: SiegValveEvent) -> None:
        self.loop.change_to_hp_keep_more()
        self.loop.sieg_valve_active()

    def before_keeping_less(self, event: SiegValveEvent) -> None:
        self.loop.change_to_hp_keep_less()
        self.loop.sieg_valve_active()

    def before_keeping_steady(self, event: SiegValveEvent) -> None:
        self.loop.sieg_valve_hold()
