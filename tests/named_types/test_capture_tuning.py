"""Tests capture.tuning type, version 000"""

import pytest

from gwsproto.named_types import CaptureTuning


def base_config() -> dict:
    return {
        "ChannelName": "buffer-depth1-device",
        "PollPeriodMs": 200,
        "CapturePeriodS": 300,
        "AsyncCapture": True,
        "AsyncCaptureDelta": 1,
        "TypeName": "capture.tuning",
        "Version": "000",
    }


def test_capture_tuning_generated() -> None:
    d = base_config()

    d2 = CaptureTuning.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_capture_tuning_axiom_1() -> None:
    d = base_config()
    d["PollPeriodMs"] = 1000
    d["CapturePeriodS"] = 1

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        CaptureTuning.model_validate(d)


def test_capture_tuning_axiom_1_multiple_when_close() -> None:
    d = base_config()
    d["PollPeriodMs"] = 700
    d["CapturePeriodS"] = 2

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        CaptureTuning.model_validate(d)


def test_capture_tuning_no_async_capture_delta_axiom() -> None:
    d = base_config()
    d["AsyncCaptureDelta"] = None

    d2 = CaptureTuning.model_validate(d).model_dump(exclude_none=True)

    assert d2 == {
        "ChannelName": "buffer-depth1-device",
        "PollPeriodMs": 200,
        "CapturePeriodS": 300,
        "AsyncCapture": True,
        "TypeName": "capture.tuning",
        "Version": "000",
    }


def test_capture_tuning_axiom_1_no_poll_period() -> None:
    d = base_config()
    d["PollPeriodMs"] = None
    d["CapturePeriodS"] = 1

    d2 = CaptureTuning.model_validate(d).model_dump(exclude_none=True)

    assert d2 == {
        "ChannelName": "buffer-depth1-device",
        "CapturePeriodS": 1,
        "AsyncCapture": True,
        "AsyncCaptureDelta": 1,
        "TypeName": "capture.tuning",
        "Version": "000",
    }
