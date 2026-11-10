from typing import Literal, Optional, Union
from typing_extensions import Self

from pydantic import ConfigDict, StrictInt, model_validator

from gwsproto.enums import FsmReportType, RelayEnergizationState
from gwsproto.property_format import (
    HandleName,
    LeftRightDotStr,
    UTCMilliseconds,
    UUID4Str,
    SpaceheatName
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class RelayPinSetAction(GwsprotoSemaType):
    Value: RelayEnergizationState

class I2cWriteBitAction(GwsprotoSemaType):
    I2cBus: SpaceheatName
    Address: StrictInt
    Register: StrictInt
    Bit: StrictInt
    Value: StrictInt

class FsmAtomicReport(GwsprotoSemaType):
    MachineHandle: HandleName
    StateEnum: str
    ReportType: FsmReportType
    Action: Optional[
        Union[
            RelayPinSetAction,
            I2cWriteBitAction,
        ]
    ] = None
    EventEnum: Optional[LeftRightDotStr] = None
    Event: Optional[str] = None
    FromState: Optional[str] = None
    ToState: Optional[str] = None
    UnixTimeMs: UTCMilliseconds
    TriggerId: UUID4Str
    TypeName: Literal["fsm.atomic.report"] = "fsm.atomic.report"
    Version: Literal["001"] = "001"

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Action SHALL be present if and only if ReportType equals Action.
        """
        if (self.Action is not None) != (self.ReportType == FsmReportType.Action):
            raise ValueError(
                "Axiom 1 (ActionPresenceConsistency) failed: Action SHALL be present "
                f"if and only if ReportType equals Action; ReportType is {self.ReportType}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: EventEnum, Event, FromState, and ToState SHALL be present if and
        only if ReportType equals Event.
        """
        event_fields_present = all(
            field is not None for field in (self.EventEnum, self.Event, self.FromState, self.ToState)
        )
        if (self.ReportType == FsmReportType.Event) != event_fields_present:
            raise ValueError(
                "Axiom 2 (EventPresenceConsistency) failed: EventEnum, Event, FromState "
                "and ToState SHALL be present if and only if ReportType equals Event; "
                f"ReportType is {self.ReportType}, EventEnum={self.EventEnum}, "
                f"Event={self.Event}, FromState={self.FromState}, ToState={self.ToState}"
            )
        return self
