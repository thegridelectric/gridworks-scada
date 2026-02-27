"""
Tests for enum main.auto.state.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import MainAutoState


def test_main_auto_state() -> None:
    assert set(MainAutoState.values()) == {
        "LocalControl",
        "LeafTransactiveNode",
        "Dormant",
    }

    assert MainAutoState.default() == MainAutoState.LocalControl
    assert MainAutoState.enum_name() == "gw1.main.auto.state"
    assert MainAutoState.enum_version() == "000"
