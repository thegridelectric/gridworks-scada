from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.property_format import UtcIso8601Seconds


class WeatherSeasonalTemplateGt(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.seasonal.template.gt/000"""

    location_alias: LeftRightDot
    temp_by_month: list[StrictInt]
    start: UtcIso8601Seconds
    id: UUID4Str
    type_name: Literal["gw.weather.seasonal.template.gt"] = (
        "gw.weather.seasonal.template.gt"
    )
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "WeatherSeasonalTemplateGt":
        """
        Axiom 1: TwelveMonths
        TempByMonth SHALL hold exactly twelve values.
        """
        if len(self.temp_by_month) != 12:
            raise ValueError(
                "Axiom 1 (TwelveMonths) failed: TempByMonth holds "
                f"{len(self.temp_by_month)} values, not twelve."
            )
        return self
