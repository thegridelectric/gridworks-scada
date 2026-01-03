from typing import Literal, Optional
from typing_extensions import Self

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator

from gwsproto.enums import FsmActionType, FsmReportType
from gwsproto.property_format import (
    HandleName,
    LeftRightDotStr,
    UTCMilliseconds,
    UUID4Str,
)


class FsmAtomicReport(BaseModel):
    MachineHandle: HandleName
    StateEnum: str
    ReportType: FsmReportType
    ActionType: Optional[FsmActionType] = None
    Action: Optional[StrictInt] = None
    EventEnum: Optional[LeftRightDotStr] = None
    Event: Optional[str] = None
    FromState: Optional[str] = None
    ToState: Optional[str] = None
    UnixTimeMs: UTCMilliseconds
    TriggerId: UUID4Str
    TypeName: Literal["fsm.atomic.report"] = "fsm.atomic.report"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Action and ActionType exist iff  ReportType is Action.
        The Optional Attributes ActionType and Action exist if and only if IsAction is true.
        """
        # Implement check for axiom 1"
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: If Action exists, then it belongs to the un-versioned enum selected in the ActionType.

        """
        # Implement check for axiom 2"
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: EventType, Event, FromState, ToState exist iff ReportType is Event.

        """
        # Implement check for axiom 3"
        return self
