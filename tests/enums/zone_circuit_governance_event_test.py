"""
Tests for enum zone.circuit.governance.event.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ZoneCircuitGovernanceEvent


def test_zone_circuit_governance_event() -> None:
    assert set(ZoneCircuitGovernanceEvent.values()) == {
        "WakeUp",
        "GoDormant",
        "SwitchToStatRules",
        "SwitchToOff",
        "SwitchToThermostatic",
    }

    assert ZoneCircuitGovernanceEvent.default() == ZoneCircuitGovernanceEvent.GoDormant
    assert ZoneCircuitGovernanceEvent.enum_name() == "zone.circuit.governance.event"
    assert ZoneCircuitGovernanceEvent.enum_version() == "000"
