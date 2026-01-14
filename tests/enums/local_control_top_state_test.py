"""
Tests for enum local.control.top.state.neb.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import LocalControlTopState


def test_local_control_top_state() -> None:
    assert set(LocalControlTopState.values()) == {
        "Dormant",
        "UsingNonElectricBackup",
        "Normal",
        "ScadaBlind",
        "Monitor"
    }

    assert LocalControlTopState.default() == LocalControlTopState.Dormant
    assert LocalControlTopState.enum_name() == "gw1.lc.top.state"
    assert LocalControlTopState.enum_version() == "000"
