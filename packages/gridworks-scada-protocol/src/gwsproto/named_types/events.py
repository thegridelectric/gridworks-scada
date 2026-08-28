from typing import Literal, Self

from gwproto.messages.event import EventBase
from pydantic import model_validator

from gwsproto.named_types.remaining_elec import RemainingElec
from gwsproto.named_types.report import Report
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class RemainingElecEvent(EventBase, GwsprotoSemaType):
    Remaining: RemainingElec
    TypeName: Literal["remaining.elec.event"] = "remaining.elec.event"
    Version: str = "000"

class ReportEvent(EventBase, GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/report.event/004"""

    Report: Report
    TypeName: Literal["report.event"] = "report.event"
    Version: Literal["004"] = "004"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ReportIdentityPropagation.
        MessageId SHALL equal Report.Id.
        """
        if self.MessageId != self.Report.Id:
            raise ValueError(
                f"Axiom 1 (ReportIdentityPropagation) failed: MessageId "
                f"{self.MessageId!r} != Report.Id {self.Report.Id!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ReportCreatedTimePropagation.
        TimeCreatedMs SHALL equal Report.MessageCreatedMs.
        """
        if self.TimeCreatedMs != self.Report.MessageCreatedMs:
            raise ValueError(
                f"Axiom 2 (ReportCreatedTimePropagation) failed: TimeCreatedMs "
                f"{self.TimeCreatedMs} != Report.MessageCreatedMs "
                f"{self.Report.MessageCreatedMs}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: ReportSourcePropagation.
        Src SHALL equal Report.FromGNodeAlias.
        """
        if self.Src != self.Report.FromGNodeAlias:
            raise ValueError(
                f"Axiom 3 (ReportSourcePropagation) failed: Src {self.Src!r} != "
                f"Report.FromGNodeAlias {self.Report.FromGNodeAlias!r}"
            )
        return self

