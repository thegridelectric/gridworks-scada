"""Type heating.forecast, version 000"""
import time
from typing import List, Literal

from gwsproto.property_format import LeftRightDotStr, UTCSeconds, UUID4Str
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class HeatingForecast(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    Time: List[UTCSeconds]
    AvgPowerKw: List[float]
    RswtF: List[float]
    RswtDeltaTF: List[float]
    WeatherUid: UUID4Str
    ForecastCreatedS: UTCSeconds = Field(default_factory=lambda: int(time.time()))
    TypeName: Literal["heating.forecast"] = "heating.forecast"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Length of all hte lists must be the same.

        """
        if len(self.AvgPowerKw) != len(self.Time):
            raise ValueError(
                f"self.AvgPowerKw should be a list of length {len(self.Time)}!"
            )
        if len(self.RswtF) != len(self.Time):
            raise ValueError(f"self.RswtF should be a list of length {len(self.Time)}!")
        if len(self.RswtDeltaTF) != len(self.Time):
            raise ValueError(
                f"self.RswtDeltaTFshould be a list of length {len(self.Time)}!"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ForecastCreatedS is less than the first second in Time
        """
        if len(self.Time) > 0:
            if self.ForecastCreatedS > self.Time[0]:
                raise ValueError(
                    "Forecast should not be created after beginning of forecasted time!"
                )

        return self
