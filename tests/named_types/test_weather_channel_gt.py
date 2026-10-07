"""Tests gw.weather.channel.gt type, version 000"""

import pytest
from gwsproto.named_types import WeatherChannelGt

from tests.named_types.weather_fixtures import bundle_dict


def channel_dict() -> dict:
    return bundle_dict()["TempObservationChannel"]


def test_weather_channel_gt_generated() -> None:
    d = channel_dict()
    assert WeatherChannelGt.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_channel_gt_axiom_1_name_not_derived() -> None:
    d = channel_dict()
    d["Name"] = "us.me.millinocket.windspeed"
    with pytest.raises(ValueError, match="Axiom 1"):
        WeatherChannelGt.model_validate(d)


def test_gw_weather_channel_gt_axiom_2_offset_not_below_period() -> None:
    d = channel_dict()
    d["EmitOffsetS"] = d["EmitPeriodS"]
    with pytest.raises(ValueError, match="Axiom 2"):
        WeatherChannelGt.model_validate(d)
