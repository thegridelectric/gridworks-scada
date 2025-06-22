"""
Tests for enum home.alone.top.state.000 from the GridWorks Type Registry.
"""

from enums import HomeAloneTopState


def test_home_alone_top_state() -> None:
    assert set(HomeAloneTopState.values()) == {
        "Dormant",
        "UsingBackupOnpeak",
        "Normal",
        "ScadaBlind",
        "Monitor"
    }

    assert HomeAloneTopState.default() == HomeAloneTopState.Dormant
    assert HomeAloneTopState.enum_name() == "home.alone.top.state"
    assert HomeAloneTopState.enum_version() == "001"
