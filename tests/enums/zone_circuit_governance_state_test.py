"""
Tests for enum zone.circuit.governance.state.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ZoneCircuitGovernanceState


def test_zone_circuit_governance_state() -> None:
    assert set(ZoneCircuitGovernanceState.values()) == {
        "Dormant",
        "StatRules",
        "Off",
        "ScadaThermostatic",
    }

    assert ZoneCircuitGovernanceState.default() == ZoneCircuitGovernanceState.Dormant
    assert ZoneCircuitGovernanceState.enum_name() == "zone.circuit.governance.state"
    assert ZoneCircuitGovernanceState.enum_version() == "000"
