from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import NonEmptyString
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.property_format import UtcIso8601Seconds
from sema_snapshot.sema.types.weather_forecast_binding import WeatherForecastBinding


class WeatherForecastBundleGt(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast.bundle.gt/002"""

    name: LeftRightDot
    display_name: NonEmptyString
    location_alias: LeftRightDot
    binding_list: list[WeatherForecastBinding]
    emit_period_s: PositiveInt
    emit_offset_s: NonNegativeInt
    start: UtcIso8601Seconds
    id: UUID4Str
    type_name: Literal["gw.weather.forecast.bundle.gt"] = (
        "gw.weather.forecast.bundle.gt"
    )
    version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "WeatherForecastBundleGt":
        """
        Axiom 1: NonEmptyBindings
        BindingList SHALL be non-empty.
        """
        if len(self.binding_list) == 0:
            raise ValueError(
                "Axiom 1 (NonEmptyBindings) failed: BindingList must be non-empty."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "WeatherForecastBundleGt":
        """
        Axiom 2: SharedSliceGrid
        Every ForecastChannel in BindingList SHALL declare identical
        SliceDurationSList.
        """
        grids = {
            b.forecast_channel.name: b.forecast_channel.slice_duration_s_list
            for b in self.binding_list
        }
        if len({tuple(g) for g in grids.values()}) > 1:
            raise ValueError(
                "Axiom 2 (SharedSliceGrid) failed: every ForecastChannel must "
                f"declare identical SliceDurationSList; got {list(grids)!r} "
                "with differing grids."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "WeatherForecastBundleGt":
        """
        Axiom 3: EmitOffsetBound
        EmitOffsetS SHALL be strictly less than EmitPeriodS.
        """
        if self.emit_offset_s >= self.emit_period_s:
            raise ValueError(
                "Axiom 3 (EmitOffsetBound) failed: EmitOffsetS "
                f"({self.emit_offset_s}) must be strictly less than EmitPeriodS "
                f"({self.emit_period_s})."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "WeatherForecastBundleGt":
        """
        Axiom 4: DistinctChannels
        ForecastChannel.Name SHALL be distinct across BindingList.
        """
        names = [b.forecast_channel.name for b in self.binding_list]
        if len(set(names)) != len(names):
            raise ValueError(
                "Axiom 4 (DistinctChannels) failed: ForecastChannel.Name must be "
                f"distinct across BindingList; got {names!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> "WeatherForecastBundleGt":
        """
        Axiom 5: DistinctQuantities
        ObservationChannel.Quantity SHALL be distinct across BindingList.
        """
        quantities = [b.observation_channel.quantity for b in self.binding_list]
        if len(set(quantities)) != len(quantities):
            raise ValueError(
                "Axiom 5 (DistinctQuantities) failed: ObservationChannel.Quantity "
                "must be distinct across BindingList; got "
                f"{[q.value for q in quantities]!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> "WeatherForecastBundleGt":
        """
        Axiom 6: NameShape
        Name SHALL equal LocationAlias + "." followed by exactly one further
        segment.
        """
        prefix = f"{self.location_alias}."
        tail = self.name[len(prefix) :] if self.name.startswith(prefix) else ""
        if not tail or "." in tail:
            raise ValueError(
                f"Axiom 6 (NameShape) failed: Name ({self.name!r}) must equal "
                f"LocationAlias + '.' + exactly one further segment "
                f"(expected prefix {prefix!r})."
            )
        return self
