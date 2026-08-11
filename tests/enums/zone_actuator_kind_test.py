"""
Tests for enum zone.actuator.kind.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ZoneActuatorKind


def test_zone_actuator_kind() -> None:
    assert set(ZoneActuatorKind.values()) == {
        "FloorLoop",
        "Fancoil",
    }

    assert ZoneActuatorKind.default() == ZoneActuatorKind.FloorLoop
    assert ZoneActuatorKind.enum_name() == "zone.actuator.kind"
    assert ZoneActuatorKind.enum_version() == "000"
