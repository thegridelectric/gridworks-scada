"""The KridaDoubleRelayBoard16 device-type record pins the panel's wiring:
markings Relay1-Relay32 across two PCF8575 boards of sixteen, the first bank
of eight on each board wired in reverse (marking 1 -> pin 7, ..., 8 -> pin 0)
and the second bank direct (9 -> pin 8, ..., 16 -> pin 15). The relay actor
resolves its pin from this record alone, so an edit here silently re-wires
every deployed panel; these tests hold the arithmetic still. The record also
carries the panel's active-low drive, which every other board lacks."""

from gwsproto.data_classes.device_types.scada_krida import (
    krida_double_relay_board_16_device_type as krida,
)
from gwsproto.enums import I2cExpanderType


def board_local_pin(marking: int) -> int:
    position = (marking - 1) % 16 + 1
    return (9 - position if position < 9 else position) - 1


def test_krida_record_pin_arithmetic() -> None:
    by_marking = {int(r.RelayName.removeprefix("Relay")): r for r in krida.I2cRelays}
    assert sorted(by_marking) == list(range(1, 33))
    for marking, relay in by_marking.items():
        assert relay.ExpanderIdx == (marking - 1) // 16 + 1, relay.RelayName
        assert relay.RegisterIndex * 8 + relay.BitIndex == board_local_pin(marking), (
            relay.RelayName
        )
    assert [board_local_pin(m) for m in (1, 8, 9, 16, 17)] == [7, 0, 8, 15, 7]


def test_krida_record_expanders_dip_selectable_pcf8575() -> None:
    assert [e.ExpanderIdx for e in krida.Expanders] == [1, 2]
    for expander in krida.Expanders:
        assert expander.ExpanderType == I2cExpanderType.Pcf8575
        assert expander.I2cAddress is None
        assert expander.AllowedI2cAddressList == list(range(0x20, 0x28))
    assert not krida.SupportsPinReadback


def test_krida_relays_energize_low() -> None:
    assert krida.RelayEnergizedLevel == 0
