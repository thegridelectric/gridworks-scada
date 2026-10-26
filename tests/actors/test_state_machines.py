"""`layout.lite` declares every state machine the scada hosts: the
declaration is derived from the layout and the ops word, validates against
the sema snapshot, and covers every machine the actors report after boot,
on a House0 house and a Nolan house."""

from pathlib import Path

import pytest

from actors.relay import UNKNOWN_STATE, Relay
from actors.state_machines import declared_state_machines
from gwsproto.enums import ActorClass, SeasonalStorageMode, ServiceMode, SiegLoopStrategy
from gwsproto.named_types import LayoutLite, OperationalParams
from sema_to_dc import load_layout
from tests.named_types.sema_oracle import assert_conforms
from tests.utils.scada_live_test_helper import ScadaLiveTest, ops_word_with

CONFIG = Path(__file__).parent.parent / "config"
HOUSES = {
    "willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
}


def house_ops(tmp_path: Path, ops_file: str, standby: bool, storage: SeasonalStorageMode) -> Path:
    return ops_word_with(
        CONFIG / ops_file,
        tmp_path / ops_file,
        standby=standby,
        service_mode=ServiceMode.Heating,
        seasonal_storage_mode=storage,
        sieg_loop_strategy=SiegLoopStrategy.HoldFullSend if "house0" in ops_file else None,
    )


@pytest.mark.parametrize("house", sorted(HOUSES))
@pytest.mark.parametrize("standby", [False, True], ids=["normal", "standby"])
def test_declaration_names_each_node_once_and_conforms(tmp_path: Path, house: str, standby: bool) -> None:
    layout_file, ops_file = HOUSES[house]
    storage = SeasonalStorageMode.BufferOnly if house == "nolan" else SeasonalStorageMode.AllTanks
    ops_path = house_ops(tmp_path, ops_file, standby, storage)
    layout = load_layout(CONFIG / layout_file, ops_path)
    ops = OperationalParams.model_validate_json(ops_path.read_text())
    machines = declared_state_machines(layout, ops)
    names = [m.NodeName for m in machines]
    assert len(names) == len(set(names))
    assert "s" in names and "auto" in names
    relays = {n.Name for n in layout.nodes.values() if n.ActorClass == ActorClass.Relay}
    assert relays <= set(names)
    normal = layout.local_control_normal_node.Name
    assert (normal in names) is not standby
    for m in machines:
        assert_conforms(m)


async def assert_reports_declared(request: pytest.FixtureRequest, layout_path: Path, ops_path: Path) -> None:
    layout = load_layout(layout_path, ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        scada = h.child1_app.scada
        relays = {
            node.Name: scada.services.get_communicator_as_type(node.Name, Relay)
            for node in scada.layout.nodes.values()
            if node.ActorClass == ActorClass.Relay
        }
        await h.await_for(
            lambda: all(relay.state != UNKNOWN_STATE for relay in relays.values()),
            "ERROR waiting for every relay to leave Unknown",
            timeout=10,
        )
        lite: LayoutLite = scada.layout_lite
        assert_conforms(lite)
        enum_by_node = {m.NodeName: m.StateEnum for m in lite.StateMachines}
        reported = {
            (ms.MachineHandle.split(".")[-1], ms.StateEnum)
            for ms in scada._data.recent_machine_states.values()
        }
        assert reported
        undeclared = sorted(
            f"{node}:{enum}" for node, enum in reported if enum_by_node.get(node) != enum
        )
        assert not undeclared, undeclared


@pytest.mark.asyncio
@pytest.mark.parametrize("house", ["willow", "nolan"])
async def test_every_reported_machine_is_declared(
    request: pytest.FixtureRequest, tmp_path: Path, house: str
) -> None:
    layout_file, ops_file = HOUSES[house]
    storage = SeasonalStorageMode.BufferOnly if house == "nolan" else SeasonalStorageMode.AllTanks
    ops_path = house_ops(tmp_path, ops_file, False, storage)
    await assert_reports_declared(request, CONFIG / layout_file, ops_path)
