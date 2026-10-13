"""Tests gw.weather.forecast.channel.gt type, version 000"""

from gwsproto.named_types import WeatherForecastChannelGt

from tests.named_types.weather_fixtures import bundle_dict
from tests.named_types.sema_oracle import assert_refused


def channel_dict() -> dict:
    return bundle_dict()["TempForecastChannel"]


def test_weather_forecast_channel_gt_generated() -> None:
    d = channel_dict()
    assert WeatherForecastChannelGt.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_channel_gt_axiom_1_slice_count() -> None:
    d = channel_dict()
    d["TotalSlices"] = d["TotalSlices"] - 1
    assert_refused(WeatherForecastChannelGt, d, match="Axiom 1")


def test_gw_weather_forecast_channel_gt_axiom_2_duration_consistency() -> None:
    d = channel_dict()
    d["ForecastDurationMinutes"] = d["ForecastDurationMinutes"] - 60
    assert_refused(WeatherForecastChannelGt, d, match="Axiom 2")


def test_gw_weather_forecast_channel_gt_axiom_3_slice_quantum() -> None:
    d = channel_dict()
    # the sum is unchanged, so only the quantum fails
    d["SliceDurationSList"] = [3500, 3700] + d["SliceDurationSList"][2:]
    assert_refused(WeatherForecastChannelGt, d, match="Axiom 3")


def test_gw_weather_forecast_channel_gt_axiom_4_name_shape() -> None:
    d = channel_dict()
    d["Name"] = d["TargetChannelName"] + ".nws.hourly96"
    assert_refused(WeatherForecastChannelGt, d, match="Axiom 4")
