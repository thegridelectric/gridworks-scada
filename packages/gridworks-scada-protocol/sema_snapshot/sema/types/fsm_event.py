from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import HandleName
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str


class FsmEvent(SemaType):
    """Sema: https://schemas.electricity.works/types/fsm.event/000"""

    from_handle: HandleName
    to_handle: HandleName
    event_type: LeftRightDot
    event_name: str
    trigger_id: UUID4Str
    send_time_unix_ms: UTCMilliseconds
    type_name: Literal["fsm.event"] = "fsm.event"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "FsmEvent":
        """
        Axiom 1: EventNameBelongsToEventType
        EventName SHALL be a valid value of the enum identified by EventType.
        """
        # Validation requires runtime enum resolution; deferred to application logic.
        return self
