from typing import Annotated, List, Literal, Optional

from pydantic import Field, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import LeftRightDotStr, UtcIso8601Seconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class WeatherForecastChannelGt(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast.channel.gt/000"""

    Name: LeftRightDotStr
    TargetChannelName: LeftRightDotStr
    Forecaster: LeftRightDotStr
    Method: LeftRightDotStr
    SourceLocator: Optional[Annotated[str, Field(min_length=1)]] = None
    TotalSlices: PositiveInt
    SliceDurationSList: List[PositiveInt]
    ForecastDurationMinutes: PositiveInt
    Start: UtcIso8601Seconds
    Id: UUID4Str
    TypeName: Literal["gw.weather.forecast.channel.gt"] = "gw.weather.forecast.channel.gt"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: SliceCount. TotalSlices equals len(SliceDurationSList)."""
        if self.TotalSlices != len(self.SliceDurationSList):
            raise ValueError(
                f"Axiom 1 (SliceCount) failed: TotalSlices ({self.TotalSlices}) must "
                f"equal the number of elements of SliceDurationSList "
                f"({len(self.SliceDurationSList)})"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: DurationConsistency. sum(SliceDurationSList) equals
        ForecastDurationMinutes * 60."""
        if sum(self.SliceDurationSList) != self.ForecastDurationMinutes * 60:
            raise ValueError(
                f"Axiom 2 (DurationConsistency) failed: sum of SliceDurationSList "
                f"({sum(self.SliceDurationSList)}) must equal ForecastDurationMinutes * 60 "
                f"({self.ForecastDurationMinutes * 60})"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """Axiom 3: SliceQuantum. Every slice duration is a positive multiple of 300."""
        offenders = [d for d in self.SliceDurationSList if d % 300 != 0]
        if offenders:
            raise ValueError(
                f"Axiom 3 (SliceQuantum) failed: every element of SliceDurationSList "
                f"must be a positive multiple of 300; got {offenders}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """Axiom 4: NameShape. Name equals TargetChannelName + ".forecast." + one
        or more further segments."""
        prefix = f"{self.TargetChannelName}.forecast."
        if not (self.Name.startswith(prefix) and len(self.Name) > len(prefix)):
            raise ValueError(
                f"Axiom 4 (NameShape) failed: Name must equal TargetChannelName + "
                f"'.forecast.' + a forecaster slug; got {self.Name!r} for target "
                f"{self.TargetChannelName!r}"
            )
        return self
