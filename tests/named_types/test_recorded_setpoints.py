"""Tests gw.recorded.setpoints type, version 000"""

import pytest

from gwsproto.named_types import RecordedSetpoints


def base_record() -> dict:
    return {
        "ScadaAlias": "d1.isone.me.versant.keene.spruce.scada",
        "SetpointList": [
            {
                "ChannelName": "zone1-bedrooms-set",
                "Value": 7000,
                "ScadaReadTimeUnixMs": 1760000000000,
                "TypeName": "single.reading",
                "Version": "000",
            }
        ],
        "TypeName": "gw.recorded.setpoints",
        "Version": "000",
    }


def test_gw_recorded_setpoints_generated() -> None:
    d = base_record()

    d2 = RecordedSetpoints.model_validate(d).model_dump(by_alias=True, exclude_none=True)

    assert d2 == d


def test_gw_recorded_setpoints_axiom_1() -> None:
    d = base_record()
    d["SetpointList"].append(dict(d["SetpointList"][0], Value=6800))

    with pytest.raises(ValueError, match="Axiom 1 \\(SetpointChannelUniqueness\\) failed"):
        RecordedSetpoints.model_validate(d)
