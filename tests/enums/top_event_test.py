"""
Tests for enum top.event.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import TopEvent


def test_top_event() -> None:
    assert set(TopEvent.values()) == {
        "AdminWakesUp",
        "AdminTimesOut",
    }

    assert TopEvent.default() == TopEvent.AdminWakesUp
    assert TopEvent.enum_name() == "top.event"
    assert TopEvent.enum_version() == "000"
