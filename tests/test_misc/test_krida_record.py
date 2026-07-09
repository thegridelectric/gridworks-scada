"""The KridaDoubleRelayBoard16 device-type record must reproduce the legacy
pin arithmetic exactly — the record is the declared form of what gw_to_pin
computed (panel markings Relay1-Relay32, first-bank inversion included). The
mux resolves pins from the record when the layout carries it; this pins the
record against edits that would silently re-wire deployed panels."""

from gwsproto.data_classes.device_types.scada_krida import (
    krida_double_relay_board_16_device_type as krida,
)

from actors.i2c_relay_multiplexer import board_from_gw_idx, gw_to_pin


def test_krida_record_matches_legacy_pin_arithmetic() -> None:
    by_marking = {
        int(r.RelayName.removeprefix("Relay")): r for r in krida.I2cRelays
    }
    assert sorted(by_marking) == list(range(1, 33))
    for marking, relay in by_marking.items():
        assert relay.ExpanderIdx == board_from_gw_idx(marking), relay.RelayName
        assert (
            relay.RegisterIndex * 8 + relay.BitIndex == gw_to_pin(marking)
        ), relay.RelayName


def test_krida_record_expanders_dip_selectable() -> None:
    assert [e.ExpanderIdx for e in krida.Expanders] == [1, 2]
    for expander in krida.Expanders:
        assert expander.I2cAddress is None
        assert expander.AllowedI2cAddressList == list(range(0x20, 0x28))
