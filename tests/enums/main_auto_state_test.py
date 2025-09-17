"""
Tests for enum main.auto.state.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import MainAutoState


def test_main_auto_state() -> None:
    assert set(MainAutoState.values()) == {
        "HomeAlone",
        "Atn",
        "Dormant",
    }

    assert MainAutoState.default() == MainAutoState.HomeAlone
    assert MainAutoState.enum_name() == "main.auto.state"
    assert MainAutoState.enum_version() == "000"
