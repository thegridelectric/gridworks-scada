from typing import List, Literal

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import Quantity, WeatherForecastFidelity
from gwsproto.property_format import LeftRightDotStr, UtcIso8601Seconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class GwWeatherForecastSeries(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast.series/000"""

    ChannelName: LeftRightDotStr
    Quantity: Quantity
    Values: List[StrictInt]
    Fidelity: WeatherForecastFidelity
    SourceUpdatedTime: UtcIso8601Seconds
    TypeName: Literal["gw.weather.forecast.series"] = "gw.weather.forecast.series"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: NonEmptyValues. Values is non-empty."""
        if len(self.Values) == 0:
            raise ValueError("Axiom 1 (NonEmptyValues) failed: Values must be non-empty")
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: ForecastNaming. ChannelName contains "forecast" as an
        interior segment."""
        if "forecast" not in self.ChannelName.split(".")[1:-1]:
            raise ValueError(
                f"Axiom 2 (ForecastNaming) failed: {self.ChannelName!r} must "
                "contain 'forecast' as an interior segment"
            )
        return self
