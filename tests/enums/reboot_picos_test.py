"""
Tests for enum reboot.picos.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import RebootPicos


def test_reboot_picos() -> None:
    assert set(RebootPicos.values()) == {"RebootPicos"}

    assert RebootPicos.default() == RebootPicos.RebootPicos
    assert RebootPicos.enum_name() == "reboot.picos"
    assert RebootPicos.enum_version() == "000"
