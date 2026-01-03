from typing import  Literal, Self
from pydantic import model_validator
from gwproto.messages.event import EventBase

from gwsproto.named_types.remaining_elec import RemainingElec
from gwsproto.named_types.report import Report


class RemainingElecEvent(EventBase):
    Remaining: RemainingElec
    TypeName: Literal["remaining.elec.event"] = "remaining.elec.event"
    Version: str = "000"

class ReportEvent(EventBase):
    Report: Report
    TypeName: Literal["report.event"] = "report.event"
    Version: str = "002"

    @model_validator(mode="after")
    def infer_base_fields(self) -> Self:
        if str(self.Report.Version) == "001":
            self.Version = "000"
        elif self.Report.Version == "002":
            self.Version = "002"
        self.MessageId = self.Report.Id
        self.TimeCreatedMs = self.Report.MessageCreatedMs
        return self
