from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import NonEmptyString
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.property_format import UtcIso8601Seconds
from sema_snapshot.sema.types.weather_channel_gt import WeatherChannelGt
from sema_snapshot.sema.types.weather_forecast_channel_gt import (
    WeatherForecastChannelGt,
)


class WeatherForecastBundleGt(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast.bundle.gt/001"""

    name: LeftRightDot
    display_name: NonEmptyString
    location_alias: LeftRightDot
    temp_forecast_channel: WeatherForecastChannelGt
    temp_observation_channel: WeatherChannelGt
    wind_speed_forecast_channel: WeatherForecastChannelGt
    wind_speed_observation_channel: WeatherChannelGt
    emit_period_s: PositiveInt
    emit_offset_s: NonNegativeInt
    start: UtcIso8601Seconds
    id: UUID4Str
    type_name: Literal["gw.weather.forecast.bundle.gt"] = (
        "gw.weather.forecast.bundle.gt"
    )
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "WeatherForecastBundleGt":
        """
        Axiom 1: SharedSliceGrid
        TempForecastChannel and WindSpeedForecastChannel SHALL declare
        identical SliceDurationSList.
        """
        if (
            self.temp_forecast_channel.slice_duration_s_list
            != self.wind_speed_forecast_channel.slice_duration_s_list
        ):
            raise ValueError(
                "Axiom 1 (SharedSliceGrid) failed: TempForecastChannel and "
                "WindSpeedForecastChannel must declare identical "
                "SliceDurationSList."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "WeatherForecastBundleGt":
        """
        Axiom 2: EmitOffsetBound
        EmitOffsetS SHALL be strictly less than EmitPeriodS.
        """
        if not self.emit_offset_s < self.emit_period_s:
            raise ValueError(
                "Axiom 2 (EmitOffsetBound) failed: EmitOffsetS "
                f"({self.emit_offset_s}) must be strictly less than "
                f"EmitPeriodS ({self.emit_period_s})."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "WeatherForecastBundleGt":
        """
        Axiom 3: DistinctChannels
        TempForecastChannel.Name SHALL differ from
        WindSpeedForecastChannel.Name.
        """
        if self.temp_forecast_channel.name == self.wind_speed_forecast_channel.name:
            raise ValueError(
                "Axiom 3 (DistinctChannels) failed: TempForecastChannel.Name "
                "and WindSpeedForecastChannel.Name are both "
                f"{self.temp_forecast_channel.name!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "WeatherForecastBundleGt":
        """
        Axiom 4: TargetBinding
        TempForecastChannel.TargetChannelName SHALL equal
        TempObservationChannel.Name, and
        WindSpeedForecastChannel.TargetChannelName SHALL equal
        WindSpeedObservationChannel.Name.
        """
        if (
            self.temp_forecast_channel.target_channel_name
            != self.temp_observation_channel.name
            or self.wind_speed_forecast_channel.target_channel_name
            != self.wind_speed_observation_channel.name
        ):
            raise ValueError(
                "Axiom 4 (TargetBinding) failed: each forecast channel's "
                "TargetChannelName must equal its paired observation "
                "channel's Name."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> "WeatherForecastBundleGt":
        """
        Axiom 5: QuantityTargeting
        TempObservationChannel.Quantity SHALL be Temperature, and
        WindSpeedObservationChannel.Quantity SHALL be WindSpeed.
        """
        if (
            self.temp_observation_channel.quantity.value != "Temperature"
            or self.wind_speed_observation_channel.quantity.value != "WindSpeed"
        ):
            raise ValueError(
                "Axiom 5 (QuantityTargeting) failed: TempObservationChannel "
                "must have Quantity Temperature and "
                "WindSpeedObservationChannel must have Quantity WindSpeed; "
                f"got {self.temp_observation_channel.quantity.value!r} / "
                f"{self.wind_speed_observation_channel.quantity.value!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> "WeatherForecastBundleGt":
        """
        Axiom 6: LocationConsistency
        TempObservationChannel.LocationAlias and
        WindSpeedObservationChannel.LocationAlias SHALL equal LocationAlias.
        """
        if (
            self.temp_observation_channel.location_alias != self.location_alias
            or self.wind_speed_observation_channel.location_alias != self.location_alias
        ):
            raise ValueError(
                "Axiom 6 (LocationConsistency) failed: both observation "
                "channels' LocationAlias must equal "
                f"{self.location_alias!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_7(self) -> "WeatherForecastBundleGt":
        """
        Axiom 7: ForecastNaming
        Name SHALL equal LocationAlias + ".forecast." followed by one or more
        further segments.
        """
        prefix = f"{self.location_alias}.forecast."
        if not (self.name.startswith(prefix) and len(self.name) > len(prefix)):
            raise ValueError(
                f"Axiom 7 (ForecastNaming) failed: {self.name!r} must equal "
                f"{prefix!r} followed by one or more further segments."
            )
        return self
