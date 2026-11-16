from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UTCSeconds
from sema_snapshot.sema.property_format import UUID4Str


class SlowDispatchContract(SemaType):
    """Sema: https://schemas.electricity.works/types/slow.dispatch.contract/001"""

    scada_alias: LeftRightDot
    start_s: UTCSeconds
    duration_minutes: PositiveInt
    avg_power_watts: StrictInt
    contract_id: UUID4Str
    dispatch_terms: LeftRightDot
    type_name: Literal["slow.dispatch.contract"] = "slow.dispatch.contract"
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "SlowDispatchContract":
        """
        Axiom 1: StartOnFiveMinutes
        StartS SHALL be a multiple of 300.
        """
        if self.start_s % 300 != 0:
            raise ValueError(
                "Axiom 1 (StartOnFiveMinutes) failed: StartS must be a multiple "
                f"of 300, got {self.start_s}."
            )
        return self
