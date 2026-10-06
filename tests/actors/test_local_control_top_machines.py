"""The top machine of each heating local control: its states and the
events that move it. Neither family's heating machine has the Standby
state, and standby has no machine."""

import pytest

from actors.local_control.house0.tou_base import LocalControlTouBase
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control.standby import StandbyLocalControl
from gwsproto.enums import LocalControlTopEvent, LocalControlTopState

HEATING_STATES = {
    LocalControlTouBase: {
        LocalControlTopState.Dormant,
        LocalControlTopState.Normal,
        LocalControlTopState.ScadaBlind,
        LocalControlTopState.UsingNonElectricBackup,
    },
    NolanBufferOnlyTou: {
        LocalControlTopState.Dormant,
        LocalControlTopState.Normal,
        LocalControlTopState.ScadaBlind,
    },
}


@pytest.mark.parametrize("machine", HEATING_STATES, ids=lambda m: m.__name__)
def test_top_machine_states(machine: type) -> None:
    states = HEATING_STATES[machine]
    assert set(machine.top_states) == states
    for transition in machine.top_transitions:
        assert transition["source"] in states
        assert transition["dest"] in states
        assert transition["trigger"] in LocalControlTopEvent.values()


def test_standby_has_no_machine() -> None:
    assert StandbyLocalControl.top_state == LocalControlTopState.Standby
    assert not hasattr(StandbyLocalControl, "top_states")
    assert not hasattr(StandbyLocalControl, "top_transitions")
    assert not hasattr(StandbyLocalControl, "trigger_top_event")


def test_top_events() -> None:
    assert set(LocalControlTopEvent.values()) == {
        "SystemCold",
        "TopGoDormant",
        "TopWakeUp",
        "MissingData",
        "DataAvailable",
        "CriticalZonesAtSetpointOffpeak",
    }
