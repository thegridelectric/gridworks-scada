"""Tests gw.weather.forecast.binding type, version 000"""

from gwsproto.named_types import WeatherForecastBinding

from tests.named_types.weather_fixtures import binding_dict
from tests.named_types.sema_oracle import assert_refused


def test_weather_forecast_binding_generated() -> None:
    d = binding_dict("Temperature")
    assert WeatherForecastBinding.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_binding_axiom_1_target_unbound() -> None:
    d = binding_dict("Temperature")
    d["ObservationChannel"]["Name"] = d["ObservationChannel"]["Name"] + ".rooftop"
    assert_refused(WeatherForecastBinding, d, match="Axiom 1")
