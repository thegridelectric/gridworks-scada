"""The top machine of each local control: its states and the events that
move it. Neither family's heating machine has the Standby state, and the
standby machine has Standby and Dormant alone."""

import pytest

from actors.local_control.house0.tou_base import LocalControlTouBase
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control.standby import StandbyLocalControl
from gwsproto.enums import LocalControlTopEvent, LocalControlTopState
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.type_helpers.command_tree_axioms import LOCAL_CONTROL_STATE_NODES

TOP_STATES = {
    LocalControlTouBase: {
        LocalControlTopState.Dormant,
        LocalControlTopState.Normal,
        LocalControlTopState.ScadaBlind,
        LocalControlTopState.InBackup,
    },
    NolanBufferOnlyTou: {
        LocalControlTopState.Dormant,
        LocalControlTopState.Normal,
        LocalControlTopState.ScadaBlind,
        LocalControlTopState.InBackup,
    },
    StandbyLocalControl: {
        LocalControlTopState.Dormant,
        LocalControlTopState.Standby,
    },
}


@pytest.mark.parametrize("machine", TOP_STATES, ids=lambda m: m.__name__)
def test_top_machine_states(machine: type) -> None:
    states = TOP_STATES[machine]
    assert set(machine.top_states) == states
    for transition in machine.top_transitions:
        assert transition["source"] in states
        assert transition["dest"] in states
        assert transition["trigger"] in LocalControlTopEvent.values()


def test_nolan_has_no_way_into_backup() -> None:
    assert not [
        t
        for t in NolanBufferOnlyTou.top_transitions
        if t["dest"] == LocalControlTopState.InBackup
    ]


def test_every_commanding_top_state_has_its_state_node() -> None:
    state_nodes = {
        LocalControlTopState.Normal: CoreNodeNames.local_control_normal,
        LocalControlTopState.InBackup: CoreNodeNames.local_control_backup,
        LocalControlTopState.ScadaBlind: CoreNodeNames.local_control_scada_blind,
        LocalControlTopState.Standby: CoreNodeNames.local_control_standby,
    }
    assert set(LocalControlTopState) - {LocalControlTopState.Dormant} == set(state_nodes)
    assert set(state_nodes.values()) == LOCAL_CONTROL_STATE_NODES


def test_top_events() -> None:
    assert set(LocalControlTopEvent.values()) == {
        "SystemCold",
        "TopGoDormant",
        "TopWakeUp",
        "MissingData",
        "DataAvailable",
        "CriticalZonesAtSetpointOffpeak",
    }
