from typing import Literal, Optional, Union
from typing_extensions import Self

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator

from gwsproto.enums import FsmReportType, RelayEnergizationState
from gwsproto.property_format import (
    HandleName,
    LeftRightDotStr,
    UTCMilliseconds,
    UUID4Str,
    SpaceheatName
)


class RelayPinSetAction(BaseModel):
    Value: RelayEnergizationState


class I2cWriteBitAction(BaseModel):
    I2cBus: SpaceheatName
    Address: StrictInt
    Register: StrictInt
    Bit: StrictInt
    Value: StrictInt


class FsmAtomicReport(BaseModel):
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
        Axiom 1: Action exists iff  ReportType is Action.

        """
        # Implement check for axiom 1"
        return self


    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 3: EventType, Event, FromState, ToState exist iff ReportType is Event.

        """
        # Implement check for axiom 3"
        return self
