"""Tests multichannel.snapshot type, version 000"""

from gwsproto.named_types import MultichannelSnapshot


def test_multichannel_snapshot_generated() -> None:
    d = {
        "HwUid": "pico_3a202a",
        "ChannelNameList": ["primary-flow", "hp-lwt", "hp-ewt"],
        "MeasurementList": [150, 4500, 3800],
        "UnitList": ["GpmTimes100", "CelsiusTimes100", "CelsiusTimes100"],
        "TypeName": "multichannel.snapshot",
        "Version": "000"
    }

    d2 =  MultichannelSnapshot.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
