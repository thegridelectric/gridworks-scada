from typing import Literal
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCSeconds
from sema_snapshot.sema.property_format import UUID4Str


class HeatingForecast(SemaType):
    """Sema: https://schemas.electricity.works/types/heating.forecast/000"""

    from_g_node_alias: LeftRightDot
    time: list[UTCSeconds]
    avg_power_kw: list[StrictFloat]
    rswt_f: list[StrictFloat]
    rswt_delta_t_f: list[StrictFloat]
    weather_uid: UUID4Str
    forecast_created_s: UTCSeconds
    type_name: Literal["heating.forecast"] = "heating.forecast"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "HeatingForecast":
        """
        Axiom 1: ListLengthConsistency
        Time, AvgPowerKw, RswtF, and RswtDeltaTF SHALL all have the same length.
        """
        lengths = {
            len(self.time),
            len(self.avg_power_kw),
            len(self.rswt_f),
            len(self.rswt_delta_t_f),
        }
        if len(lengths) > 1:
            raise ValueError(
                "Axiom 1 failed: time, avg_power_kw, rswt_f, and rswt_delta_t_f must "
                "all have the same length."
            )
        return self
