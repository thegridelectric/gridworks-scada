"""Tests gw.weather.forecast.series type, version 000"""

from gwsproto.named_types import GwWeatherForecastSeries

from tests.named_types.weather_fixtures import series_dict
from tests.named_types.sema_oracle import assert_refused


def test_gw_weather_forecast_series_generated() -> None:
    d = series_dict("Temperature")
    assert GwWeatherForecastSeries.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_series_axiom_1_empty_values() -> None:
    d = series_dict("Temperature")
    d["Values"] = []
    assert_refused(GwWeatherForecastSeries, d, match="Axiom 1")


def test_gw_weather_forecast_series_axiom_2_no_forecast_segment() -> None:
    d = series_dict("Temperature")
    d["ChannelName"] = "kmlt.temperature.nws.hourly"
    assert_refused(GwWeatherForecastSeries, d, match="Axiom 2")
