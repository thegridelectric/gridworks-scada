from typing import List, Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.named_types.gw_weather_forecast_series import GwWeatherForecastSeries
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds, UtcIso8601Seconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class GwWeatherForecast(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast/001"""

    BundleName: LeftRightDotStr
    MessageCreatedMs: UTCMilliseconds
    FirstSliceStart: UtcIso8601Seconds
    SeriesList: List[GwWeatherForecastSeries]
    TypeName: Literal["gw.weather.forecast"] = "gw.weather.forecast"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: NonEmptySeriesList. SeriesList is non-empty."""
        if len(self.SeriesList) == 0:
            raise ValueError("Axiom 1 (NonEmptySeriesList) failed: SeriesList must be non-empty")
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: EqualValueLengths. Every series has the same len(Values)."""
        lengths = {s.ChannelName: len(s.Values) for s in self.SeriesList}
        if len(set(lengths.values())) > 1:
            raise ValueError(
                "Axiom 2 (EqualValueLengths) failed: every series must have the "
                f"same len(Values); got {lengths!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """Axiom 3: DistinctChannels. ChannelName is distinct across SeriesList."""
        names = [s.ChannelName for s in self.SeriesList]
        if len(set(names)) != len(names):
            raise ValueError(
                "Axiom 3 (DistinctChannels) failed: ChannelName must be distinct "
                f"across SeriesList; got {names!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """Axiom 4: DistinctQuantities. Quantity is distinct across SeriesList."""
        quantities = [s.Quantity for s in self.SeriesList]
        if len(set(quantities)) != len(quantities):
            raise ValueError(
                "Axiom 4 (DistinctQuantities) failed: Quantity must be distinct "
                f"across SeriesList; got {[q.value for q in quantities]!r}"
            )
        return self
