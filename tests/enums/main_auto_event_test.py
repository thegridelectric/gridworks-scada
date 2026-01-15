"""
Tests for enum gw1.main.auto.event.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import MainAutoEvent


def test_main_auto_event() -> None:
    assert set(MainAutoEvent.values()) == {
        "DispatchContractLive",
        "ContractGracePeriodEnds",
        "LtnReleasesControl",
        "AllyGivesUp",
        "AutoGoesDormant",
        "AutoWakesUp",
    }

    assert MainAutoEvent.default() == MainAutoEvent.AutoWakesUp
    assert MainAutoEvent.enum_name() == "gw1.main.auto.event"
    assert MainAutoEvent.enum_version() == "000"
