"""Tests gw.weather.forecast.channel.gt type, version 000"""

import pytest
from gwsproto.named_types import WeatherForecastChannelGt

from tests.named_types.weather_fixtures import bundle_dict


def channel_dict() -> dict:
    return bundle_dict()["TempForecastChannel"]


def test_weather_forecast_channel_gt_generated() -> None:
    d = channel_dict()
    assert WeatherForecastChannelGt.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_channel_gt_axiom_1_slice_count() -> None:
    d = channel_dict()
    d["TotalSlices"] = d["TotalSlices"] - 1
    with pytest.raises(ValueError, match="Axiom 1"):
        WeatherForecastChannelGt.model_validate(d)


def test_gw_weather_forecast_channel_gt_axiom_2_duration_consistency() -> None:
    d = channel_dict()
    d["ForecastDurationMinutes"] = d["ForecastDurationMinutes"] - 60
    with pytest.raises(ValueError, match="Axiom 2"):
        WeatherForecastChannelGt.model_validate(d)


def test_gw_weather_forecast_channel_gt_axiom_3_slice_quantum() -> None:
    d = channel_dict()
    # the sum is unchanged, so only the quantum fails
    d["SliceDurationSList"] = [3500, 3700] + d["SliceDurationSList"][2:]
    with pytest.raises(ValueError, match="Axiom 3"):
        WeatherForecastChannelGt.model_validate(d)


def test_gw_weather_forecast_channel_gt_axiom_4_name_shape() -> None:
    d = channel_dict()
    d["Name"] = d["TargetChannelName"] + ".nws.hourly96"
    with pytest.raises(ValueError, match="Axiom 4"):
        WeatherForecastChannelGt.model_validate(d)
