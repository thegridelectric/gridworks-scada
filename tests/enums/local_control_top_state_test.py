"""
Tests for the gwsproto twin of gw2.lc.top.state 000.
"""

from gwsproto.enums import LocalControlTopState


def test_local_control_top_state() -> None:
    assert set(LocalControlTopState.values()) == {
        "Dormant",
        "UsingNonElectricBackup",
        "Normal",
        "ScadaBlind",
        "Standby",
    }

    assert LocalControlTopState.default() == LocalControlTopState.Dormant
    assert LocalControlTopState.enum_name() == "gw2.lc.top.state"
    assert LocalControlTopState.enum_version() == "000"
