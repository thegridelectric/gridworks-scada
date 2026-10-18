from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UtcIso8601Seconds
from sema_snapshot.sema.types.weather_forecast_series import WeatherForecastSeries


class WeatherForecast(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast/001"""

    bundle_name: LeftRightDot
    message_created_ms: UTCMilliseconds
    first_slice_start: UtcIso8601Seconds
    series_list: list[WeatherForecastSeries]
    type_name: Literal["gw.weather.forecast"] = "gw.weather.forecast"
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "WeatherForecast":
        """
        Axiom 1: NonEmptySeriesList
        SeriesList SHALL be non-empty.
        """
        if len(self.series_list) == 0:
            raise ValueError(
                "Axiom 1 (NonEmptySeriesList) failed: SeriesList must be non-empty."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "WeatherForecast":
        """
        Axiom 2: EqualValueLengths
        Every series in SeriesList SHALL have the same len(Values).
        """
        lengths = {s.channel_name: len(s.values) for s in self.series_list}
        if len(set(lengths.values())) > 1:
            raise ValueError(
                "Axiom 2 (EqualValueLengths) failed: every series must have the "
                f"same len(Values); got {lengths!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "WeatherForecast":
        """
        Axiom 3: DistinctChannels
        ChannelName SHALL be distinct across SeriesList.
        """
        names = [s.channel_name for s in self.series_list]
        if len(set(names)) != len(names):
            raise ValueError(
                "Axiom 3 (DistinctChannels) failed: ChannelName must be distinct "
                f"across SeriesList; got {names!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "WeatherForecast":
        """
        Axiom 4: DistinctQuantities
        Quantity SHALL be distinct across SeriesList.
        """
        quantities = [s.quantity for s in self.series_list]
        if len(set(quantities)) != len(quantities):
            raise ValueError(
                "Axiom 4 (DistinctQuantities) failed: Quantity must be distinct "
                f"across SeriesList; got {[q.value for q in quantities]!r}."
            )
        return self
