"""
Tests for enum top.state.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import TopState


def test_top_state() -> None:
    assert set(TopState.values()) == {
        "Auto",
        "Admin",
    }

    assert TopState.default() == TopState.Auto
    assert TopState.enum_name() == "top.state"
    assert TopState.enum_version() == "000"
