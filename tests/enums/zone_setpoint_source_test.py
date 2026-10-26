"""
Tests for enum zone.setpoint.source.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ZoneSetpointSource


def test_zone_setpoint_source() -> None:
    assert set(ZoneSetpointSource.values()) == {
        "FromThermostat",
        "Learned",
    }

    assert ZoneSetpointSource.default() == ZoneSetpointSource.Learned
    assert ZoneSetpointSource.enum_name() == "zone.setpoint.source"
    assert ZoneSetpointSource.enum_version() == "000"
