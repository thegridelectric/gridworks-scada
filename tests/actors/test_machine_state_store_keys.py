"""The scada's machine store keys every path by the hosting node, the
handle's last segment: `recent_machine_states`, which becomes the report's
StateList, and `latest_machine_state`. A command-tree change rewrites a
node's handle; its states before and after the change stay one machine,
one row per report, whichever path (SingleMachineState or MachineStates)
delivered them. A second enum reported for the same node is a conflict on
either path."""

from pathlib import Path

import pytest

from gwsproto.enums import RelayClosedOrOpen
from gwsproto.named_types import MachineStates, SingleMachineState
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
RELAY = "hp-scada-ops-relay"
T0 = 1_760_000_000_000


@pytest.fixture
def scada():
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    actor = app.prime_actor
    actor._send_to = lambda dst, payload, src=None: None
    return actor


def single(handle: str, state: RelayClosedOrOpen, unix_ms: int) -> SingleMachineState:
    return SingleMachineState(
        MachineHandle=handle,
        StateEnum=RelayClosedOrOpen.enum_name(),
        State=state,
        UnixMs=unix_ms,
    )


def test_a_handle_change_inside_a_window_keeps_one_row_per_node(scada) -> None:
    relay = scada.layout.node(RELAY)
    auto_handle = relay.handle
    scada.process_single_machine_state(relay, single(auto_handle, RelayClosedOrOpen.RelayOpen, T0))
    relay.Handle = f"admin.{RELAY}"
    scada.process_single_machine_state(relay, single(relay.handle, RelayClosedOrOpen.RelayClosed, T0 + 1000))
    relay.Handle = auto_handle
    scada.process_single_machine_state(relay, single(relay.handle, RelayClosedOrOpen.RelayOpen, T0 + 2000))

    rows = [ms for ms in scada._data.recent_machine_states.values() if ms.MachineHandle.split(".")[-1] == RELAY]
    assert len(rows) == 1
    assert RELAY in scada._data.recent_machine_states
    assert rows[0].StateList == [RelayClosedOrOpen.RelayOpen, RelayClosedOrOpen.RelayClosed, RelayClosedOrOpen.RelayOpen]
    assert rows[0].UnixMsList == [T0, T0 + 1000, T0 + 2000]
    assert scada._data.latest_machine_state[RELAY].State == RelayClosedOrOpen.RelayOpen
    assert scada._data.latest_machine_state[RELAY].UnixMs == T0 + 2000

    report = scada._data.make_report(T0 // 1000)
    assert [ms.MachineHandle.split(".")[-1] for ms in report.StateList].count(RELAY) == 1


def test_both_paths_share_the_node_key(scada) -> None:
    relay = scada.layout.node(RELAY)
    scada.process_single_machine_state(relay, single(relay.handle, RelayClosedOrOpen.RelayOpen, T0))
    scada.process_machine_states(
        relay,
        MachineStates(
            MachineHandle=relay.handle,
            StateEnum=RelayClosedOrOpen.enum_name(),
            StateList=[RelayClosedOrOpen.RelayClosed],
            UnixMsList=[T0 + 1000],
        ),
    )
    assert scada._data.recent_machine_states[RELAY].StateList == [
        RelayClosedOrOpen.RelayOpen,
        RelayClosedOrOpen.RelayClosed,
    ]


def test_a_second_enum_on_one_node_is_a_conflict(scada) -> None:
    relay = scada.layout.node(RELAY)
    scada.process_single_machine_state(relay, single(relay.handle, RelayClosedOrOpen.RelayOpen, T0))
    other = SingleMachineState(
        MachineHandle=f"admin.{RELAY}",
        StateEnum="valve.open.or.closed",
        State="ValveOpen",
        UnixMs=T0 + 1000,
    )
    with pytest.raises(Exception, match="conflicting state machines"):
        scada.process_single_machine_state(relay, other)
