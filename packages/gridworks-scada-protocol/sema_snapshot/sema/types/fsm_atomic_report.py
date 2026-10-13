from typing import Any, Literal
from pydantic import ConfigDict, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import FsmReportType
from sema_snapshot.sema.property_format import HandleName
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str


class FsmAtomicReport(SemaType):
    """Sema: https://schemas.electricity.works/types/fsm.atomic.report/001"""

    machine_handle: HandleName
    state_enum: str
    report_type: FsmReportType
    action: dict[str, Any] | None = None
    event_enum: LeftRightDot | None = None
    event: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    unix_time_ms: UTCMilliseconds
    trigger_id: UUID4Str
    type_name: Literal["fsm.atomic.report"] = "fsm.atomic.report"
    version: Literal["001"] = "001"

    model_config = ConfigDict(**(SemaType.model_config | {"extra": "allow"}))

    @model_validator(mode="after")
    def check_axiom_1(self) -> "FsmAtomicReport":
        """
        Axiom 1: ActionPresenceConsistency
        Action SHALL be present if and only if ReportType equals Action.
        """
        if (self.report_type == "Action") != (self.action is not None):
            raise ValueError(
                "Axiom 1 failed: action must be present if and only if report_type is Action."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "FsmAtomicReport":
        """
        Axiom 2: EventPresenceConsistency
        EventEnum, Event, FromState, and ToState SHALL be present if and only if ReportType
        equals Event.
        """
        event_fields_present = all(
            field is not None
            for field in (self.event_enum, self.event, self.from_state, self.to_state)
        )
        if (self.report_type == "Event") != event_fields_present:
            raise ValueError(
                "Axiom 2 failed: event fields must be present if and only if report_type is Event."
            )
        return self
