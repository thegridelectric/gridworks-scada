"""Tests gw.weather.forecast.bundle.gt type, version 000"""

import pytest
from gwsproto.named_types import WeatherForecastBundleGt

from tests.named_types.weather_fixtures import bundle_dict


def test_weather_forecast_bundle_gt_generated() -> None:
    d = bundle_dict()
    assert WeatherForecastBundleGt.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_bundle_gt_axiom_1_different_slice_grids() -> None:
    d = bundle_dict()
    ch = d["WindSpeedForecastChannel"]
    ch["SliceDurationSList"] = [1800] * (ch["TotalSlices"] * 2)
    ch["TotalSlices"] = len(ch["SliceDurationSList"])
    with pytest.raises(ValueError, match="Axiom 1"):
        WeatherForecastBundleGt.model_validate(d)


def test_gw_weather_forecast_bundle_gt_axiom_2_offset_not_below_period() -> None:
    d = bundle_dict()
    d["EmitOffsetS"] = d["EmitPeriodS"]
    with pytest.raises(ValueError, match="Axiom 2"):
        WeatherForecastBundleGt.model_validate(d)


def test_gw_weather_forecast_bundle_gt_axiom_3_same_forecast_channel() -> None:
    d = bundle_dict()
    d["WindSpeedForecastChannel"] = d["TempForecastChannel"]
    d["WindSpeedObservationChannel"] = d["TempObservationChannel"]
    with pytest.raises(ValueError, match="Axiom 3"):
        WeatherForecastBundleGt.model_validate(d)


def test_gw_weather_forecast_bundle_gt_axiom_4_target_unbound() -> None:
    d = bundle_dict()
    d["TempObservationChannel"]["Name"] = d["LocationAlias"] + ".temperature.rooftop"
    with pytest.raises(ValueError, match="Axiom 4"):
        WeatherForecastBundleGt.model_validate(d)


def test_gw_weather_forecast_bundle_gt_axiom_5_wrong_quantity() -> None:
    d = bundle_dict()
    temp, wind = d["TempObservationChannel"], d["WindSpeedObservationChannel"]
    d["TempObservationChannel"], d["WindSpeedObservationChannel"] = wind, temp
    d["TempForecastChannel"]["TargetChannelName"] = wind["Name"]
    d["WindSpeedForecastChannel"]["TargetChannelName"] = temp["Name"]
    d["TempForecastChannel"]["Name"] = wind["Name"] + ".forecast.nws.hourly96"
    d["WindSpeedForecastChannel"]["Name"] = temp["Name"] + ".forecast.nws.hourly96"
    with pytest.raises(ValueError, match="Axiom 5"):
        WeatherForecastBundleGt.model_validate(d)


def test_gw_weather_forecast_bundle_gt_axiom_6_location_mismatch() -> None:
    d = bundle_dict()
    d["LocationAlias"] = "us.me.bangor"
    d["Name"] = "us.me.bangor.forecast.nws.hourly96"
    with pytest.raises(ValueError, match="Axiom 6"):
        WeatherForecastBundleGt.model_validate(d)


def test_gw_weather_forecast_bundle_gt_axiom_7_name_not_under_location() -> None:
    d = bundle_dict()
    d["Name"] = "us.me.bangor.forecast.nws.hourly96"
    with pytest.raises(ValueError, match="Axiom 7"):
        WeatherForecastBundleGt.model_validate(d)
