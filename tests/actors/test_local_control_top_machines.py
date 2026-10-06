"""The top machine of each heating local control: its states and the
events that move it. Neither family's machine has a monitoring state; a
house that only watches is a standby posture."""

import pytest

from actors.local_control.house0.tou_base import LocalControlTouBase
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from gwsproto.enums import LocalControlTopEvent, LocalControlTopState

MACHINES = [LocalControlTouBase, NolanBufferOnlyTou]


@pytest.mark.parametrize("machine", MACHINES, ids=lambda m: m.__name__)
def test_top_machine_states(machine: type) -> None:
    states = set(LocalControlTopState) - {LocalControlTopState.Monitor}
    assert set(machine.top_states) == states
    for transition in machine.top_transitions:
        assert transition["source"] in states
        assert transition["dest"] in states
        assert transition["trigger"] in LocalControlTopEvent.values()


def test_top_events() -> None:
    assert set(LocalControlTopEvent.values()) == {
        "SystemCold",
        "TopGoDormant",
        "TopWakeUp",
        "MissingData",
        "DataAvailable",
        "CriticalZonesAtSetpointOffpeak",
    }
