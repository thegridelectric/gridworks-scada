from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import Quantity
from gwsproto.named_types.weather_channel_gt import WeatherChannelGt
from gwsproto.named_types.weather_forecast_channel_gt import WeatherForecastChannelGt
from gwsproto.property_format import LeftRightDotStr, UtcIso8601Seconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class WeatherForecastBundleGt(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast.bundle.gt/000"""

    Name: LeftRightDotStr
    DisplayName: Annotated[str, Field(min_length=1)]
    LocationAlias: LeftRightDotStr
    TempForecastChannel: WeatherForecastChannelGt
    TempObservationChannel: WeatherChannelGt
    WindSpeedForecastChannel: WeatherForecastChannelGt
    WindSpeedObservationChannel: WeatherChannelGt
    EmitPeriodS: PositiveInt
    EmitOffsetS: NonNegativeInt
    Start: UtcIso8601Seconds
    Id: UUID4Str
    TypeName: Literal["gw.weather.forecast.bundle.gt"] = "gw.weather.forecast.bundle.gt"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: SharedSliceGrid. Both forecast channels declare identical
        SliceDurationSList."""
        if (
            self.TempForecastChannel.SliceDurationSList
            != self.WindSpeedForecastChannel.SliceDurationSList
        ):
            raise ValueError(
                "Axiom 1 (SharedSliceGrid) failed: TempForecastChannel and "
                "WindSpeedForecastChannel must declare identical SliceDurationSList"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: EmitOffsetBound. EmitOffsetS is strictly less than EmitPeriodS."""
        if not self.EmitOffsetS < self.EmitPeriodS:
            raise ValueError(
                f"Axiom 2 (EmitOffsetBound) failed: EmitOffsetS ({self.EmitOffsetS}) "
                f"must be strictly less than EmitPeriodS ({self.EmitPeriodS})"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """Axiom 3: DistinctChannels. The two forecast channels have different Names."""
        if self.TempForecastChannel.Name == self.WindSpeedForecastChannel.Name:
            raise ValueError(
                "Axiom 3 (DistinctChannels) failed: TempForecastChannel.Name and "
                f"WindSpeedForecastChannel.Name are both {self.TempForecastChannel.Name!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """Axiom 4: TargetBinding. Each forecast channel's TargetChannelName equals
        its paired observation channel's Name."""
        if (
            self.TempForecastChannel.TargetChannelName != self.TempObservationChannel.Name
            or self.WindSpeedForecastChannel.TargetChannelName
            != self.WindSpeedObservationChannel.Name
        ):
            raise ValueError(
                "Axiom 4 (TargetBinding) failed: each forecast channel's "
                "TargetChannelName must equal its paired observation channel's Name"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """Axiom 5: QuantityTargeting. The temperature observation channel is
        Temperature and the wind speed one is WindSpeed."""
        if (
            self.TempObservationChannel.Quantity != Quantity.Temperature
            or self.WindSpeedObservationChannel.Quantity != Quantity.WindSpeed
        ):
            raise ValueError(
                "Axiom 5 (QuantityTargeting) failed: TempObservationChannel must have "
                "Quantity Temperature and WindSpeedObservationChannel Quantity WindSpeed; "
                f"got {self.TempObservationChannel.Quantity.value!r} / "
                f"{self.WindSpeedObservationChannel.Quantity.value!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> Self:
        """Axiom 6: LocationConsistency. Both observation channels carry the
        bundle's LocationAlias."""
        if (
            self.TempObservationChannel.LocationAlias != self.LocationAlias
            or self.WindSpeedObservationChannel.LocationAlias != self.LocationAlias
        ):
            raise ValueError(
                "Axiom 6 (LocationConsistency) failed: both observation channels' "
                f"LocationAlias must equal {self.LocationAlias!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_7(self) -> Self:
        """Axiom 7: ForecastNaming. Name equals LocationAlias + ".forecast." + one
        or more further segments."""
        prefix = f"{self.LocationAlias}.forecast."
        if not (self.Name.startswith(prefix) and len(self.Name) > len(prefix)):
            raise ValueError(
                f"Axiom 7 (ForecastNaming) failed: {self.Name!r} must equal {prefix!r} "
                "followed by one or more further segments"
            )
        return self
