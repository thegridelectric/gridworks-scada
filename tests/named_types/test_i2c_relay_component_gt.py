"""Tests i2c.relay.component.gt type, version 000"""

import pytest

from gwsproto.named_types import I2cRelayComponentGt


def base_component() -> dict:
    return {
        "ComponentId": "a754e7d9-f690-4602-93bc-c5fc91f4df2e",
        "BoardComponentId": "9359f967-4bcd-4846-a47e-2344cd6f611d",
        "RelayName": "Zone1Failsafe",
        "ConfigList": [
            {
                "ChannelName": "zone1-bedrooms-failsafe-relay",
                "ActorName": "zone1-bedrooms-failsafe-relay",
                "WiringConfig": "DoubleThrow",
                "EventType": "change.zone.call.source",
                "DeEnergizingEvent": "SwitchToWallThermostat",
                "EnergizingEvent": "SwitchToScada",
                "StateType": "zone.call.source",
                "DeEnergizedState": "WallThermostat",
                "EnergizedState": "Scada",
                "TypeName": "relay.control.config",
                "Version": "000",
            }
        ],
        "DisplayName": "Zone 1 Bedrooms Failsafe Relay",
        "TypeName": "i2c.relay.component.gt",
        "Version": "000",
    }


def test_i2c_relay_component_gt_generated() -> None:
    d = base_component()

    d2 = I2cRelayComponentGt.model_validate(d).model_dump(
        by_alias=True, exclude_none=True
    )

    assert d2 == d


def test_i2c_relay_component_gt_axiom_1() -> None:
    d = base_component()
    d["ConfigList"] = d["ConfigList"] * 2

    with pytest.raises(ValueError, match="Axiom 1 \\(ExactlyOneConfig\\) failed"):
        I2cRelayComponentGt.model_validate(d)

    d["ConfigList"] = []

    with pytest.raises(ValueError, match="Axiom 1 \\(ExactlyOneConfig\\) failed"):
        I2cRelayComponentGt.model_validate(d)
