from typing import Any, Literal

from gwproto.messages.event import EventBase
from gwsproto.named_types.remaining_elec import RemainingElec


class RemainingElecEvent(EventBase):
    Remaining: RemainingElec
    TypeName: Literal["remaining.elec.event"] = "remaining.elec.event"
    Version: Literal["000"] = "000"

    def __init__(self, **data: dict[str, Any]) -> None:
        super().__init__(**data)
