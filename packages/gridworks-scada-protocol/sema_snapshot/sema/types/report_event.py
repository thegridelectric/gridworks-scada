from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.report import Report


class ReportEvent(SemaType):
    """Sema: https://schemas.electricity.works/types/report.event/004"""

    message_id: UUID4Str
    time_created_ms: UTCMilliseconds
    src: LeftRightDot
    report: Report
    type_name: Literal["report.event"] = "report.event"
    version: Literal["004"] = "004"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ReportEvent":
        """
        Axiom 1: ReportIdentityPropagation
        MessageId SHALL equal Report.Id.
        """
        if self.message_id != self.report.id:
            raise ValueError(
                f"ReportIdentityPropagation: message_id {self.message_id} must equal report.id {self.report.id}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "ReportEvent":
        """
        Axiom 2: ReportCreatedTimePropagation
        TimeCreatedMs SHALL equal Report.MessageCreatedMs.
        """
        if self.time_created_ms != self.report.message_created_ms:
            raise ValueError(
                f"ReportCreatedTimePropagation: time_created_ms {self.time_created_ms} must equal report.message_created_ms {self.report.message_created_ms}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "ReportEvent":
        """
        Axiom 3: ReportSourcePropagation
        Src SHALL equal Report.FromGNodeAlias.
        """
        if self.src != self.report.from_g_node_alias:
            raise ValueError(
                f"ReportSourcePropagation: src {self.src} must equal report.from_g_node_alias {self.report.from_g_node_alias}."
            )
        return self
