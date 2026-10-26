"""
Tests for enum zone.call.circuit.state.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ZoneCallCircuitState


def test_zone_call_circuit_state() -> None:
    assert set(ZoneCallCircuitState.values()) == {
        "Dormant",
        "Released",
        "TakingHold",
        "Held",
        "StartingCall",
        "Calling",
        "StoppingCall",
        "Releasing",
    }

    assert ZoneCallCircuitState.default() == ZoneCallCircuitState.Released
    assert ZoneCallCircuitState.enum_name() == "zone.call.circuit.state"
    assert ZoneCallCircuitState.enum_version() == "000"
