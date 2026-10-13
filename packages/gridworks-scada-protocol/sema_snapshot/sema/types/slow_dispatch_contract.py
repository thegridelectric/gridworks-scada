from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UTCSeconds
from sema_snapshot.sema.property_format import UUID4Str


class SlowDispatchContract(SemaType):
    """Sema: https://schemas.electricity.works/types/slow.dispatch.contract/000"""

    scada_alias: LeftRightDot
    start_s: UTCSeconds
    duration_minutes: PositiveInt
    avg_power_watts: StrictInt
    oil_boiler_on: bool
    contract_id: UUID4Str
    type_name: Literal["slow.dispatch.contract"] = "slow.dispatch.contract"
    version: Literal["000"] = "000"

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

    @model_validator(mode="after")
    def check_axiom_2(self) -> "SlowDispatchContract":
        """
        Axiom 2: OilBoilerDrawsNoPower
        If OilBoilerOn is true, AvgPowerWatts SHALL be 0.
        """
        if self.oil_boiler_on and self.avg_power_watts != 0:
            raise ValueError(
                "Axiom 2 (OilBoilerDrawsNoPower) failed: OilBoilerOn requires "
                f"AvgPowerWatts 0, got {self.avg_power_watts}."
            )
        return self
