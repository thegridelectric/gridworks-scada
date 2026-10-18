from typing import Annotated, List, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.named_types.weather_forecast_binding import WeatherForecastBinding
from gwsproto.property_format import LeftRightDotStr, UtcIso8601Seconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class WeatherForecastBundleGt(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast.bundle.gt/002"""

    Name: LeftRightDotStr
    DisplayName: Annotated[str, Field(min_length=1)]
    LocationAlias: LeftRightDotStr
    BindingList: List[WeatherForecastBinding]
    EmitPeriodS: PositiveInt
    EmitOffsetS: NonNegativeInt
    Start: UtcIso8601Seconds
    Id: UUID4Str
    TypeName: Literal["gw.weather.forecast.bundle.gt"] = "gw.weather.forecast.bundle.gt"
    Version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: NonEmptyBindings. BindingList is non-empty."""
        if len(self.BindingList) == 0:
            raise ValueError("Axiom 1 (NonEmptyBindings) failed: BindingList must be non-empty")
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: SharedSliceGrid. Every ForecastChannel declares identical
        SliceDurationSList."""
        grids = {b.ForecastChannel.Name: b.ForecastChannel.SliceDurationSList for b in self.BindingList}
        if len({tuple(g) for g in grids.values()}) > 1:
            raise ValueError(
                "Axiom 2 (SharedSliceGrid) failed: every ForecastChannel must "
                f"declare identical SliceDurationSList; got {list(grids)!r} with differing grids"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """Axiom 3: EmitOffsetBound. EmitOffsetS is strictly less than EmitPeriodS."""
        if not self.EmitOffsetS < self.EmitPeriodS:
            raise ValueError(
                f"Axiom 3 (EmitOffsetBound) failed: EmitOffsetS ({self.EmitOffsetS}) "
                f"must be strictly less than EmitPeriodS ({self.EmitPeriodS})"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """Axiom 4: DistinctChannels. ForecastChannel.Name is distinct across
        BindingList."""
        names = [b.ForecastChannel.Name for b in self.BindingList]
        if len(set(names)) != len(names):
            raise ValueError(
                "Axiom 4 (DistinctChannels) failed: ForecastChannel.Name must be "
                f"distinct across BindingList; got {names!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """Axiom 5: DistinctQuantities. ObservationChannel.Quantity is distinct
        across BindingList."""
        quantities = [b.ObservationChannel.Quantity for b in self.BindingList]
        if len(set(quantities)) != len(quantities):
            raise ValueError(
                "Axiom 5 (DistinctQuantities) failed: ObservationChannel.Quantity "
                f"must be distinct across BindingList; got {[q.value for q in quantities]!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> Self:
        """Axiom 6: NameShape. Name equals LocationAlias + "." + exactly one
        further segment."""
        prefix = f"{self.LocationAlias}."
        tail = self.Name[len(prefix) :] if self.Name.startswith(prefix) else ""
        if not tail or "." in tail:
            raise ValueError(
                f"Axiom 6 (NameShape) failed: Name ({self.Name!r}) must equal "
                f"LocationAlias + '.' + exactly one further segment (expected prefix {prefix!r})"
            )
        return self
