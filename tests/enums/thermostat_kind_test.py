"""
Tests for enum thermostat.kind.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ThermostatKind


def test_thermostat_kind() -> None:
    assert set(ThermostatKind.values()) == {
        "MechanicalDial",
        "HoneywellViaHubitat",
    }

    assert ThermostatKind.default() == ThermostatKind.MechanicalDial
    assert ThermostatKind.enum_name() == "thermostat.kind"
    assert ThermostatKind.enum_version() == "000"
