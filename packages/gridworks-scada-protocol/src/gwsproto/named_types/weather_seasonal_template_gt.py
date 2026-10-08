from typing import List, Literal

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import LeftRightDotStr, UtcIso8601Seconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class WeatherSeasonalTemplateGt(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.seasonal.template.gt/000"""

    LocationAlias: LeftRightDotStr
    TempByMonth: List[StrictInt]
    Start: UtcIso8601Seconds
    Id: UUID4Str
    TypeName: Literal["gw.weather.seasonal.template.gt"] = "gw.weather.seasonal.template.gt"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: TwelveMonths. TempByMonth holds exactly twelve values."""
        if len(self.TempByMonth) != 12:
            raise ValueError(
                f"Axiom 1 (TwelveMonths) failed: TempByMonth holds {len(self.TempByMonth)} values, not twelve"
            )
        return self
