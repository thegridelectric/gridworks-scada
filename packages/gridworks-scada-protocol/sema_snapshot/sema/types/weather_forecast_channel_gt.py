from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import NonEmptyString
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.property_format import UtcIso8601Seconds


class WeatherForecastChannelGt(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast.channel.gt/000"""

    name: LeftRightDot
    target_channel_name: LeftRightDot
    forecaster: LeftRightDot
    method: LeftRightDot
    source_locator: NonEmptyString | None = None
    total_slices: PositiveInt
    slice_duration_s_list: list[PositiveInt]
    forecast_duration_minutes: PositiveInt
    start: UtcIso8601Seconds
    id: UUID4Str
    type_name: Literal["gw.weather.forecast.channel.gt"] = (
        "gw.weather.forecast.channel.gt"
    )
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "WeatherForecastChannelGt":
        """
        Axiom 1: SliceCount
        TotalSlices SHALL equal the number of elements of SliceDurationSList.
        """
        if self.total_slices != len(self.slice_duration_s_list):
            raise ValueError(
                "Axiom 1 (SliceCount) failed: TotalSlices "
                f"({self.total_slices}) must equal the number of elements of "
                f"SliceDurationSList ({len(self.slice_duration_s_list)})."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "WeatherForecastChannelGt":
        """
        Axiom 2: DurationConsistency
        The sum of SliceDurationSList SHALL equal ForecastDurationMinutes times 60.
        """
        if sum(self.slice_duration_s_list) != self.forecast_duration_minutes * 60:
            raise ValueError(
                "Axiom 2 (DurationConsistency) failed: sum of "
                f"SliceDurationSList ({sum(self.slice_duration_s_list)}) must "
                f"equal ForecastDurationMinutes * 60 "
                f"({self.forecast_duration_minutes * 60})."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "WeatherForecastChannelGt":
        """
        Axiom 3: SliceQuantum
        Every element of SliceDurationSList SHALL be a positive multiple of 300.
        """
        offenders = [d for d in self.slice_duration_s_list if d % 300 != 0]
        if offenders:
            raise ValueError(
                "Axiom 3 (SliceQuantum) failed: every element of "
                "SliceDurationSList must be a positive multiple of 300; got "
                f"{offenders}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "WeatherForecastChannelGt":
        """
        Axiom 4: NameShape
        Name SHALL equal TargetChannelName + ".forecast." followed by one or more
        further segments.
        """
        prefix = f"{self.target_channel_name}.forecast."
        if not (self.name.startswith(prefix) and len(self.name) > len(prefix)):
            raise ValueError(
                "Axiom 4 (NameShape) failed: Name must equal "
                f"TargetChannelName + '.forecast.' + a forecaster slug; got "
                f"'{self.name}' for target '{self.target_channel_name}'."
            )
        return self
