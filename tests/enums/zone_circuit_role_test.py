"""
Tests for enum zone.circuit.role.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ZoneCircuitRole


def test_zone_circuit_role() -> None:
    assert set(ZoneCircuitRole.values()) == {
        "Baseload",
        "RapidResponse",
    }

    assert ZoneCircuitRole.default() == ZoneCircuitRole.Baseload
    assert ZoneCircuitRole.enum_name() == "zone.circuit.role"
    assert ZoneCircuitRole.enum_version() == "000"
