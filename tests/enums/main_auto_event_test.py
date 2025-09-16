"""
Tests for enum main.auto.event.001 from the GridWorks Type Registry.
"""

from gwsproto.enums import MainAutoEvent


def test_main_auto_event() -> None:
    assert set(MainAutoEvent.values()) == {
        "DispatchContractLive",
        "ContractGracePeriodEnds",
        "AtnReleasesControl",
        "AllyGivesUp",
        "AutoGoesDormant",
        "AutoWakesUp",
    }

    assert MainAutoEvent.default() == MainAutoEvent.AutoWakesUp
    assert MainAutoEvent.enum_name() == "main.auto.event"
    assert MainAutoEvent.enum_version() == "001"
