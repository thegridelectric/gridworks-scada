from typing import Literal

from gwsproto.property_format import (
    HandleName,
    LeftRightDotStr,
    UTCMilliseconds,
    UUID4Str,
)
from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self


class FsmEvent(BaseModel):
    """
    Finite State Machine Event Command.

    A message sent to a SpaceheatNode wher ethe Node implements a finite state machine. The
    message is intended to be an FSM Events (aka Trigger) that allow a state machine to react
    (by starting a Transition and any side-effect Actions).

    [More info](https://gridworks-protocol.readthedocs.io/en/latest/finite-state-machines.html)
    """

    FromHandle: HandleName
    ToHandle: HandleName
    EventType: LeftRightDotStr
    EventName: str
    TriggerId: UUID4Str
    SendTimeUnixMs: UTCMilliseconds
    TypeName: Literal["fsm.event"] = "fsm.event"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: EventName must belong to the enum selected in the EventType.

        """
        # Implement check for axiom 1"
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: FromHandle must be the immediate boss of ToHandle.
        """
        if "multiplexer" in self.ToHandle:
            return self
        immediate_boss = ".".join(self.ToHandle.split(".")[:-1])
        if immediate_boss != self.FromHandle:
            raise ValueError(
                f"FromHandle {self.FromHandle} must be immediate boss of ToHandle {self.ToHandle}"
            )
        return self
