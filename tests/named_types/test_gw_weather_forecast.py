"""Tests gw.weather.forecast type, version 000"""

import pytest
from gwsproto.named_types import GwWeatherForecast

from tests.named_types.weather_fixtures import forecast_dict


def test_gw_weather_forecast_generated() -> None:
    d = forecast_dict()
    assert GwWeatherForecast.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_axiom_1_empty_values() -> None:
    d = forecast_dict()
    d["TempValues"] = []
    d["WindSpeedValues"] = []
    with pytest.raises(ValueError, match="Axiom 1"):
        GwWeatherForecast.model_validate(d)


def test_gw_weather_forecast_axiom_2_unequal_lengths() -> None:
    d = forecast_dict()
    d["WindSpeedValues"] = d["WindSpeedValues"][:-1]
    with pytest.raises(ValueError, match="Axiom 2"):
        GwWeatherForecast.model_validate(d)


def test_gw_weather_forecast_axiom_3_same_channel() -> None:
    d = forecast_dict()
    d["WindSpeedChannelName"] = d["TempChannelName"]
    with pytest.raises(ValueError, match="Axiom 3"):
        GwWeatherForecast.model_validate(d)


def test_gw_weather_forecast_axiom_4_no_forecast_segment() -> None:
    d = forecast_dict()
    d["BundleName"] = "us.me.millinocket.nws.hourly96"
    with pytest.raises(ValueError, match="Axiom 4"):
        GwWeatherForecast.model_validate(d)
