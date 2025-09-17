"""
Tests for enum turn.hp.on.off.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import TurnHpOnOff


def test_turn_hp_on_off() -> None:
    assert set(TurnHpOnOff.values()) == {
        "TurnOn",
        "TurnOff",
    }

    assert TurnHpOnOff.default() == TurnHpOnOff.TurnOn
    assert TurnHpOnOff.enum_name() == "turn.hp.on.off"
    assert TurnHpOnOff.enum_version() == "000"
