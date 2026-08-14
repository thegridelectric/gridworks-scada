"""Tests i2c.multichannel.dt.relay.component.gt type, version 004"""

import pytest

from gwsproto.named_types import I2cMultichannelDtRelayComponentGt


def base_relay_config(actor_name: str, relay_idx: int, channel_name: str) -> dict:
    return {
        "ActorName": actor_name,
        "ChannelName": channel_name,
        "DeEnergizedState": "RelayClosed",
        "DeEnergizingEvent": "CloseRelay",
        "EnergizedState": "RelayOpen",
        "EnergizingEvent": "OpenRelay",
        "EventType": "change.relay.state",
        "RelayIdx": relay_idx,
        "StateType": "relay.closed.or.open",
        "TypeName": "relay.actor.config",
        "Version": "003",
        "WiringConfig": "NormallyClosed",
    }


def base_component() -> dict:
    return {
        "ComponentId": "b95e75a3-1483-484f-954f-65d202d50e6d",
        "DeviceType": "KridaDoubleRelayBoard16",
        "ConfigList": [
            base_relay_config("relay1", 1, "vdc-relay1"),
            base_relay_config("relay2", 2, "tstat-common-relay2"),
        ],
        "DisplayName": "i2c krida relay boards",
        "I2cBus": "bus-1",
        "I2cAddressList": [32, 33],
        "TypeName": "i2c.multichannel.dt.relay.component.gt",
        "Version": "005",
    }


def test_i2c_multichannel_dt_relay_component_gt_generated() -> None:
    d = base_component()

    d2 = I2cMultichannelDtRelayComponentGt.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_i2c_multichannel_dt_relay_component_gt_actor_name_uniqueness() -> None:
    d = base_component()
    d["ConfigList"][1]["ActorName"] = "relay1"

    with pytest.raises(ValueError, match="Duplicate ActorName\\(s\\)"):
        I2cMultichannelDtRelayComponentGt.model_validate(d)


def test_i2c_multichannel_dt_relay_component_gt_relay_idx_uniqueness() -> None:
    d = base_component()
    d["ConfigList"][1]["RelayIdx"] = 1

    with pytest.raises(ValueError, match="Duplicate RelayIdx\\(s\\)"):
        I2cMultichannelDtRelayComponentGt.model_validate(d)
