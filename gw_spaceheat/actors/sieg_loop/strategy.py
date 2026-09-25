"""What every Siegenthaler-loop strategy shares: the message the loop sends
hp-boss, the choice of strategy from the ops word, and the interface the
facade drives."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal, Optional

from gwsproto.enums import ActuationAuthority, HpBossState, SiegLoopStrategy
from gwsproto.named_types import House0FamilyParams, OperationalParams
from pydantic import BaseModel

if TYPE_CHECKING:
    from actors.sieg_loop import SiegLoop


class SiegLoopReady(BaseModel):
    """The loop tells hp-boss the valve is set for a heat pump start."""

    TypeName: Literal["sieg.loop.ready"] = "sieg.loop.ready"
    Version: str = "000"


def selected_strategy(ops: OperationalParams) -> Optional[SiegLoopStrategy]:
    """The strategy the loop runs under this ops word: the House0 family's
    SiegLoopStrategy, except that Standby runs HoldFullSend whatever the
    field says, since the power-less posture is full send. None for a
    family with no loop."""
    family = ops.FamilyParams
    if not isinstance(family, House0FamilyParams):
        return None
    if ops.ActuationAuthority is ActuationAuthority.Standby:
        return SiegLoopStrategy.HoldFullSend
    return family.SiegLoopStrategy


class SiegStrategy(ABC):
    """One way of driving the loop's valve. The facade owns the valve, the
    tick and the hp-boss subscription and hands the strategy each event;
    the strategy decides what the valve does."""

    def __init__(self, loop: "SiegLoop") -> None:
        self.loop = loop

    @abstractmethod
    def on_actuators_ready(self) -> None:
        """The scada's actuators are ready; the valve may move."""

    @abstractmethod
    def on_hp_boss_state(self, state: HpBossState) -> None:
        """hp-boss reported a state."""

    @abstractmethod
    def tick(self) -> None:
        """The loop's control interval elapsed."""

    @abstractmethod
    def resume(self) -> None:
        """The loop is back under automatic control after a command: put
        the valve where the strategy wants it."""
