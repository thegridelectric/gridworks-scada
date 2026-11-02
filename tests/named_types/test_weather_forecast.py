"""Tests gw.weather.forecast type, version 002"""

from gwsproto.named_types import WeatherForecast

from tests.named_types.weather_fixtures import forecast_dict
from tests.named_types.sema_oracle import assert_refused


def test_gw_weather_forecast_generated() -> None:
    d = forecast_dict()
    assert WeatherForecast.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_axiom_1_empty_series_list() -> None:
    d = forecast_dict()
    d["SeriesList"] = []
    assert_refused(WeatherForecast, d, match="Axiom 1")


def test_gw_weather_forecast_axiom_2_unequal_lengths() -> None:
    d = forecast_dict()
    d["SeriesList"][1]["Values"] = d["SeriesList"][1]["Values"][:-1]
    assert_refused(WeatherForecast, d, match="Axiom 2")


def test_gw_weather_forecast_axiom_3_same_channel() -> None:
    d = forecast_dict()
    d["SeriesList"][1]["ChannelName"] = d["SeriesList"][0]["ChannelName"]
    assert_refused(WeatherForecast, d, match="Axiom 3")


def test_gw_weather_forecast_axiom_4_same_quantity() -> None:
    d = forecast_dict()
    d["SeriesList"][1]["Quantity"] = d["SeriesList"][0]["Quantity"]
    assert_refused(WeatherForecast, d, match="Axiom 4")
