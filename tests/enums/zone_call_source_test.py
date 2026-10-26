"""
Tests for enum zone.call.source.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ZoneCallSource


def test_zone_call_source() -> None:
    assert set(ZoneCallSource.values()) == {
        "WallThermostat",
        "Scada",
    }

    assert ZoneCallSource.default() == ZoneCallSource.WallThermostat
    assert ZoneCallSource.enum_name() == "zone.call.source"
    assert ZoneCallSource.enum_version() == "000"
