from typing import  Literal
from gwproto.messages.event import EventBase

from gwsproto.named_types.remaining_elec import RemainingElec
from gwsproto.named_types.report import Report
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class RemainingElecEvent(EventBase, GwsprotoSemaType):
    Remaining: RemainingElec
    TypeName: Literal["remaining.elec.event"] = "remaining.elec.event"
    Version: str = "000"

class ReportEvent(EventBase, GwsprotoSemaType):
    Report: Report
    TypeName: Literal["report.event"] = "report.event"
    Version: Literal["003"] = "003"

