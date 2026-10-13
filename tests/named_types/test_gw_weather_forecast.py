"""Tests gw.weather.forecast type, version 000"""

from gwsproto.named_types import GwWeatherForecast

from tests.named_types.weather_fixtures import forecast_dict
from tests.named_types.sema_oracle import assert_refused


def test_gw_weather_forecast_generated() -> None:
    d = forecast_dict()
    assert GwWeatherForecast.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_axiom_1_empty_values() -> None:
    d = forecast_dict()
    d["TempValues"] = []
    d["WindSpeedValues"] = []
    assert_refused(GwWeatherForecast, d, match="Axiom 1")


def test_gw_weather_forecast_axiom_2_unequal_lengths() -> None:
    d = forecast_dict()
    d["WindSpeedValues"] = d["WindSpeedValues"][:-1]
    assert_refused(GwWeatherForecast, d, match="Axiom 2")


def test_gw_weather_forecast_axiom_3_same_channel() -> None:
    d = forecast_dict()
    d["WindSpeedChannelName"] = d["TempChannelName"]
    assert_refused(GwWeatherForecast, d, match="Axiom 3")


def test_gw_weather_forecast_axiom_4_no_forecast_segment() -> None:
    d = forecast_dict()
    d["BundleName"] = "us.me.millinocket.nws.hourly96"
    assert_refused(GwWeatherForecast, d, match="Axiom 4")
