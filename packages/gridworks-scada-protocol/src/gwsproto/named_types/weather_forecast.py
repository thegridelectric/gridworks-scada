"""Type weather.forecast, version 000"""
import time
import uuid
from typing import List, Literal

from gwsproto.property_format import  LeftRightDotStr, UTCSeconds, UUID4Str
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class WeatherForecast(BaseModel):
    """
    Weather Forecast Raw.

    A type meant to be used for weather forecast data from a direct third-party source.
    """

    FromGNodeAlias: LeftRightDotStr
    WeatherChannelName: LeftRightDotStr
    Time: List[UTCSeconds]
    OatF: List[float]
    WindSpeedMph: List[float]
    WeatherUid: UUID4Str = Field(default_factory=lambda: str(uuid.uuid4()))
    ForecastCreatedS: UTCSeconds = Field(default_factory=lambda: int(time.time()))
    TypeName: Literal["weather.forecast"] = "weather.forecast"
    Version: str = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Length of all the lists (Time, OatF, WindspeedMph) must be the same.

        """
        if len(self.OatF) != len(self.Time):
            raise ValueError(f"self.OatFshould be a list of length {len(self.Time)}!")
        if len(self.WindSpeedMph) != len(self.Time):
            raise ValueError(f"self.OatF should be a list of length {len(self.Time)}!")

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
