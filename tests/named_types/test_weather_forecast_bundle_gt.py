"""Tests gw.weather.forecast.bundle.gt type, version 002"""

from gwsproto.named_types import WeatherForecastBundleGt

from tests.named_types.weather_fixtures import bundle_dict
from tests.named_types.sema_oracle import assert_refused


def test_weather_forecast_bundle_gt_generated() -> None:
    d = bundle_dict()
    assert WeatherForecastBundleGt.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_forecast_bundle_gt_axiom_1_empty_binding_list() -> None:
    d = bundle_dict()
    d["BindingList"] = []
    assert_refused(WeatherForecastBundleGt, d, match="Axiom 1")


def test_gw_weather_forecast_bundle_gt_axiom_2_different_slice_grids() -> None:
    d = bundle_dict()
    ch = d["BindingList"][1]["ForecastChannel"]
    ch["SliceDurationSList"] = [1800] * (ch["TotalSlices"] * 2)
    ch["TotalSlices"] = len(ch["SliceDurationSList"])
    assert_refused(WeatherForecastBundleGt, d, match="Axiom 2")


def test_gw_weather_forecast_bundle_gt_axiom_3_offset_not_below_period() -> None:
    d = bundle_dict()
    d["EmitOffsetS"] = d["EmitPeriodS"]
    assert_refused(WeatherForecastBundleGt, d, match="Axiom 3")


def test_gw_weather_forecast_bundle_gt_axiom_4_same_forecast_channel() -> None:
    d = bundle_dict()
    wind = d["BindingList"][1]
    wind["ForecastChannel"]["Name"] = d["BindingList"][0]["ForecastChannel"]["Name"]
    wind["ForecastChannel"]["TargetChannelName"] = d["BindingList"][0]["ForecastChannel"]["TargetChannelName"]
    wind["ObservationChannel"]["Name"] = d["BindingList"][0]["ObservationChannel"]["Name"]
    wind["ObservationChannel"]["Quantity"] = d["BindingList"][0]["ObservationChannel"]["Quantity"]
    # Axiom 5 (DistinctQuantities) fails too; the oracle names the one its runtime reaches first.
    assert_refused(WeatherForecastBundleGt, d, match="Axiom 4")


def test_gw_weather_forecast_bundle_gt_axiom_5_same_quantity() -> None:
    d = bundle_dict()
    wind = d["BindingList"][1]
    wind["ObservationChannel"]["Quantity"] = "Temperature"
    wind["ObservationChannel"]["Name"] = "kmlt.temperature.rooftop"
    wind["ForecastChannel"]["TargetChannelName"] = "kmlt.temperature.rooftop"
    wind["ForecastChannel"]["Name"] = "kmlt.temperature.rooftop.forecast.nws.hourly"
    assert_refused(WeatherForecastBundleGt, d, match="Axiom 5")


def test_gw_weather_forecast_bundle_gt_axiom_6_name_not_one_segment_under_location() -> None:
    d = bundle_dict()
    d["Name"] = "us.me.millinocket.forecast.moose"
    assert_refused(WeatherForecastBundleGt, d, match="Axiom 6")
