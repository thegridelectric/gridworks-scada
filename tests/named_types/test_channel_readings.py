"""Tests channel.readings type, version 002"""


from gwsproto.named_types import ChannelReadings
from tests.named_types.sema_oracle import assert_refused


def test_channel_readings_generated() -> None:
    d = {
        "ChannelName": "buffer-depth1",
        "ValueList": [14920, 14890],
        "ScadaReadTimeUnixMsList": [1731168353695, 1731168413695],
        "TypeName": "channel.readings",
        "Version": "002",
    }

    d2 = ChannelReadings.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_channel_readings_list_length_axiom() -> None:
    d = {
        "ChannelName": "buffer-depth1",
        "ValueList": [14920, 14890],
        "ScadaReadTimeUnixMsList": [1731168353695],
        "TypeName": "channel.readings",
        "Version": "002",
    }

    assert_refused(ChannelReadings, d, match="Axiom 1 violated!")
