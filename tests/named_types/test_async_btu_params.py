"""Tests async.btu.params type, version 000"""

from gwsproto.named_types import AsyncBtuParams


def test_async_btu_params_generated() -> None:
    d = {
        "HwUid": "pico_3a202a",
        "ActorNodeName": "primary-btu",
        "FlowChannelName": "primary-flow",
        "SendHz": False,
        "ReadCtVoltage": False,
        "HotChannelName": "hp-lwt",
        "ColdChannelName": "hp-ewt",
        "CapturePeriodS": 60,
        "GallonsPerPulse": 0.0009,
        "AsyncCaptureDeltaGpmX100": 10,
        "AsyncCaptureDeltaCelsiusX100": 20,
        "AsyncCaptureDeltaCtVoltsX100": 20,
        "TypeName": "async.btu.params",
        "Version": "000",
    }

    d2 = AsyncBtuParams.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
