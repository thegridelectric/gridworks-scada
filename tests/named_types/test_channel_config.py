"""Tests channel.config type, version 000"""

import pytest

from gwsproto.named_types import ChannelConfig


def base_config() -> dict:
    return {
        "ChannelName": "buffer-depth1-device",
        "PollPeriodMs": 200,
        "CapturePeriodS": 300,
        "AsyncCapture": True,
        "AsyncCaptureDelta": 1,
        "Exponent": 0,
        "Unit": "Unitless",
        "TypeName": "channel.config",
        "Version": "000",
    }


def test_channel_config_generated() -> None:
    d = base_config()

    d2 = ChannelConfig.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_channel_config_axiom_1() -> None:
    d = base_config()
    d["AsyncCaptureDelta"] = None

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        ChannelConfig.model_validate(d)


def test_channel_config_axiom_2_capture_must_exceed_poll() -> None:
    d = base_config()
    d["PollPeriodMs"] = 1000
    d["CapturePeriodS"] = 1

    with pytest.raises(ValueError, match="Axiom 2 violated!"):
        ChannelConfig.model_validate(d)


def test_channel_config_axiom_2_multiple_when_close() -> None:
    d = base_config()
    d["PollPeriodMs"] = 700
    d["CapturePeriodS"] = 2

    with pytest.raises(ValueError, match="Axiom 2 violated!"):
        ChannelConfig.model_validate(d)


def test_channel_config_axiom_2_no_poll_period() -> None:
    d = base_config()
    d["PollPeriodMs"] = None
    d["CapturePeriodS"] = 1

    d2 = ChannelConfig.model_validate(d).model_dump(exclude_none=True)

    assert d2 == {
        "ChannelName": "buffer-depth1-device",
        "CapturePeriodS": 1,
        "AsyncCapture": True,
        "AsyncCaptureDelta": 1,
        "Exponent": 0,
        "Unit": "Unitless",
        "TypeName": "channel.config",
        "Version": "000",
    }
