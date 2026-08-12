"""Tests the relay actor's layout-driven i2c resolution facts: the TCA9555
register map and the config-declared FSM vocabulary maps."""

import pytest

from actors.relay import EVENT_ENUM_BY_NAME, STATE_ENUM_BY_NAME
from drivers import tca9555
from gwsproto.enums import (
    ChangeRelayState,
    ChangeValveState,
    ChangeZoneCallSource,
    RelayClosedOrOpen,
    ValveOpenOrClosed,
    ZoneCallSource,
)


def test_tca9555_register_map() -> None:
    assert tca9555.input_register(tca9555.OUTPUT_PORT_0) == tca9555.INPUT_PORT_0
    assert tca9555.input_register(tca9555.OUTPUT_PORT_1) == tca9555.INPUT_PORT_1
    assert tca9555.config_register(tca9555.OUTPUT_PORT_0) == tca9555.CONFIG_PORT_0
    assert tca9555.config_register(tca9555.OUTPUT_PORT_1) == tca9555.CONFIG_PORT_1

    for not_an_output_register in (0, 1, 6, 7):
        with pytest.raises(ValueError):
            tca9555.input_register(not_an_output_register)
        with pytest.raises(ValueError):
            tca9555.config_register(not_an_output_register)


def test_relay_fsm_vocabulary_maps() -> None:
    """The three control vocabularies the spruce roster declares resolve by
    their config EventType/StateType names."""
    assert EVENT_ENUM_BY_NAME["change.relay.state"] is ChangeRelayState
    assert EVENT_ENUM_BY_NAME["change.zone.call.source"] is ChangeZoneCallSource
    assert EVENT_ENUM_BY_NAME["change.valve.state"] is ChangeValveState
    assert STATE_ENUM_BY_NAME["relay.closed.or.open"] is RelayClosedOrOpen
    assert STATE_ENUM_BY_NAME["zone.call.source"] is ZoneCallSource
    assert STATE_ENUM_BY_NAME["valve.open.or.closed"] is ValveOpenOrClosed
