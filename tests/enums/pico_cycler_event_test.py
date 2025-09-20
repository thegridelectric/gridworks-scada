"""
Tests for enum pico.cycler.event.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import PicoCyclerEvent


def test_pico_cycler_event() -> None:
    assert set(PicoCyclerEvent.values()) == {
        "WakeUp",
        "GoDormant",
        "PicoMissing",
        "ConfirmOpened",
        "StartClosing",
        "ConfirmClosed",
        "ConfirmRebooted",
        "ShakeZombies",
        "RebootDud",
    }

    assert PicoCyclerEvent.default() == PicoCyclerEvent.ConfirmRebooted
    assert PicoCyclerEvent.enum_name() == "pico.cycler.event"
    assert PicoCyclerEvent.enum_version() == "000"
