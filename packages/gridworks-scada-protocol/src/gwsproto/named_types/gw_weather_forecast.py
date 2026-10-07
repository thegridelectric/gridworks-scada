from typing import List, Literal

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import WeatherForecastFidelity
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds, UtcIso8601Seconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class GwWeatherForecast(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast/000"""

    BundleName: LeftRightDotStr
    SourceUpdatedTime: UtcIso8601Seconds
    MessageCreatedMs: UTCMilliseconds
    Fidelity: WeatherForecastFidelity
    FirstSliceStart: UtcIso8601Seconds
    TempChannelName: LeftRightDotStr
    TempValues: List[StrictInt]
    WindSpeedChannelName: LeftRightDotStr
    WindSpeedValues: List[StrictInt]
    TypeName: Literal["gw.weather.forecast"] = "gw.weather.forecast"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: NonEmptyValues. TempValues and WindSpeedValues are non-empty."""
        if len(self.TempValues) == 0 or len(self.WindSpeedValues) == 0:
            raise ValueError(
                "Axiom 1 (NonEmptyValues) failed: TempValues and WindSpeedValues "
                "must be non-empty"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: EqualValueLengths. len(TempValues) equals len(WindSpeedValues)."""
        if len(self.TempValues) != len(self.WindSpeedValues):
            raise ValueError(
                f"Axiom 2 (EqualValueLengths) failed: len(TempValues)="
                f"{len(self.TempValues)} must equal len(WindSpeedValues)="
                f"{len(self.WindSpeedValues)}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """Axiom 3: DistinctChannels. TempChannelName differs from WindSpeedChannelName."""
        if self.TempChannelName == self.WindSpeedChannelName:
            raise ValueError(
                "Axiom 3 (DistinctChannels) failed: TempChannelName and "
                f"WindSpeedChannelName are both {self.TempChannelName!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """Axiom 4: ForecastNaming. BundleName (a), TempChannelName (b) and
        WindSpeedChannelName (c) each contain "forecast" as an interior segment."""
        for clause, value in (
            ("a", self.BundleName),
            ("b", self.TempChannelName),
            ("c", self.WindSpeedChannelName),
        ):
            if "forecast" not in value.split(".")[1:-1]:
                raise ValueError(
                    f"Axiom 4 (ForecastNaming, clause {clause}) failed: {value!r} must "
                    "contain 'forecast' as an interior segment"
                )
        return self
