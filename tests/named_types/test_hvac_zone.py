"""Tests gw1.hvac.zone type, version 000"""

from gwsproto.named_types import HvacZone


def base_zone() -> dict:
    return {
        "Name": "zone1-down",
        "Critical": True,
        "KwhPerDegF": 2.5,
        "TempChannelName": "zone1-down-temp",
        "TypeName": "gw1.hvac.zone",
        "Version": "000",
    }


def test_hvac_zone_generated() -> None:
    d = base_zone()

    d2 = HvacZone.model_validate(d).model_dump(by_alias=True, exclude_none=True)

    assert d2 == d


def test_hvac_zone_temp_channel_optional() -> None:
    d = base_zone()
    del d["TempChannelName"]

    zone = HvacZone.model_validate(d)

    assert zone.TempChannelName is None
