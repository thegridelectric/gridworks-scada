"""
Tests for enum pico.cycler.state.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import PicoCyclerState


def test_pico_cycler_state() -> None:
    assert set(PicoCyclerState.values()) == {
        "Dormant",
        "PicosLive",
        "RelayOpening",
        "RelayOpen",
        "RelayClosing",
        "PicosRebooting",
        "AllZombies",
    }

    assert PicoCyclerState.default() == PicoCyclerState.PicosLive
    assert PicoCyclerState.enum_name() == "pico.cycler.state"
    assert PicoCyclerState.enum_version() == "000"
