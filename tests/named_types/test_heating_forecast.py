"""Tests heating.forecast type, version 000"""

from gwsproto.named_types import HeatingForecast


def test_heating_forecast_generated() -> None:
    d = {
        "FromGNodeAlias": 'd1.isone.me.versant.beech.scada',
        "Time": [1736812800],
        "AvgPowerKw": [13.2],
        "RswtF": [154.2],
        "RswtDeltaTF": [15],
        "WeatherUid": 'a4bafdae-1e89-414a-b3fd-a01b39a5ae38',
        "ForecastCreatedS": 1736812780,
        "TypeName": "heating.forecast",
        "Version": "000",
    }

    d2 = HeatingForecast.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
