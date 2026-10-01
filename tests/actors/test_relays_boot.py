"""Every node that is the direct boss of an actuator boots its actuators:
once the actuators are ready, every relay in the layout leaves Unknown
within seconds of the scada starting, under every local-control machine
the loader can select and every sieg-loop strategy. A standby row also
proves the standby posture: the relays the normal node claims sit
de-energized except the ops word's EnergizedStandbyRelays, the 0-10V
outputs at their power-on level, hp-boss at HpOff, the sieg loop (House0)
in HoldFullSend. Admin taking the tree and disturbing it (the heat pump
on, a relay energized) leaves nothing behind: on release the standby
machine re-sets the posture and hp-boss is HpOff again.

The rows are an each-choice covering (a 1-wise covering array), not the
product of the axes: every value of every axis appears in at least one
row, so the row count is the size of the largest axis, and adding a value
to an axis adds one row rather than multiplying them. The axes are
independent except for one constraint the ops word imposes: Standby runs
HoldFullSend whatever the field says (`actors/sieg_loop/strategy.py`
`selected_strategy`), so the Standby rows carry HoldFullSend.
`test_rows_cover_every_axis_value` fails when an axis grows without a
row covering the new value."""

import json
import time
import uuid
from pathlib import Path
from typing import NamedTuple

import pytest

from actors.hp_boss import HpBoss
from actors.local_control_loader import LocalControl
from actors.relay import Relay, UNKNOWN_STATE
from actors.sieg_loop import SiegLoop
from actors.sieg_loop.hold_full_send import HoldFullSend
from actors.zero_ten_outputer import ZeroTenOutputer
from gwsproto.enums import (
    ActorClass,
    HpBossState,
    LocalControlStandbyTopState,
    SeasonalStorageMode,
    ServiceMode,
    SiegLoopStrategy,
    TurnHpOnOff,
)
from gwsproto.enums.top_state import TopState
from gwsproto.named_types import AdminDispatch, AdminReleaseControl, FsmEvent
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from sema_to_dc import load_layout
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
WILLOW = ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")
ORANGE = ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json")
NOLAN = ("gw.nolan.layout.json", "gw.nolan.operational.params.json")


class LocalControlChoice(NamedTuple):
    """One row of the loader's selection table
    (`actors/local_control_loader.py`): the authored facts and the machine
    they select."""

    machine: str
    standby: bool
    storage: SeasonalStorageMode
    service: ServiceMode


# Axis 1: every local-control machine the loader can pick, House0 then Nolan.
HOUSE0_CONTROLS = (
    LocalControlChoice("AllTanksTouLocalControl", False, SeasonalStorageMode.AllTanks, ServiceMode.Heating),
    LocalControlChoice("BufferOnlyTouLocalControl", False, SeasonalStorageMode.BufferOnly, ServiceMode.Heating),
    LocalControlChoice("StandbyLocalControl", True, SeasonalStorageMode.AllTanks, ServiceMode.Heating),
)
NOLAN_CONTROLS = (
    LocalControlChoice("NolanCoolingTou", False, SeasonalStorageMode.AllTanks, ServiceMode.Cooling),
    LocalControlChoice("StandbyLocalControl", True, SeasonalStorageMode.AllTanks, ServiceMode.Cooling),
)
# Axis 2: every sieg-loop strategy the loop constructs (`actors/sieg_loop`).
LOOP_STRATEGIES = (SiegLoopStrategy.HoldFullSend, SiegLoopStrategy.StratProtect)
# Axis 3: every test layout.
LAYOUTS = {"willow": WILLOW, "orange": ORANGE, "nolan": NOLAN}


class Row(NamedTuple):
    """One boot to run: a layout under one local-control selection and, on
    House0, one sieg-loop strategy."""

    layout: str
    local_control: LocalControlChoice
    loop_strategy: SiegLoopStrategy | None


ROWS = (
    Row("willow", HOUSE0_CONTROLS[0], SiegLoopStrategy.StratProtect),
    Row("orange", HOUSE0_CONTROLS[1], SiegLoopStrategy.HoldFullSend),
    Row("willow", HOUSE0_CONTROLS[2], SiegLoopStrategy.HoldFullSend),  # Standby forces HoldFullSend
    Row("nolan", NOLAN_CONTROLS[0], None),
    Row("nolan", NOLAN_CONTROLS[1], None),
)


def test_rows_cover_every_axis_value() -> None:
    assert {row.local_control for row in ROWS} == set(HOUSE0_CONTROLS) | set(NOLAN_CONTROLS)
    assert {row.loop_strategy for row in ROWS if row.loop_strategy} == set(LOOP_STRATEGIES)
    assert {row.layout for row in ROWS} == set(LAYOUTS)
    for row in ROWS:
        if row.local_control.standby and row.loop_strategy is not None:
            assert row.loop_strategy is SiegLoopStrategy.HoldFullSend


def row_ops(tmp_path: Path, ops_file: str, row: Row) -> Path:
    """The layout's ops artifact with the row's selection."""
    ops = json.loads((CONFIG / ops_file).read_text())
    ops["Standby"] = row.local_control.standby
    ops["ServiceMode"] = row.local_control.service.value
    if row.local_control.standby:
        ops["AcceptsDispatch"] = False
        ops["DispatchRefusalReason"] = "Standby"
    ops["FamilyParams"]["SeasonalStorageMode"] = row.local_control.storage.value
    if row.loop_strategy is not None:
        ops["FamilyParams"]["SiegLoopStrategy"] = row.loop_strategy.value
    path = tmp_path / ops_file
    path.write_text(json.dumps(ops))
    return path


def assert_standby_posture(h: ScadaLiveTest, relays: dict[str, Relay], energized: list[str]) -> None:
    """The standby posture once the relays have booted: every relay the
    normal node claims is de-energized except the listed ones, the 0-10V
    outputs hold their power-on level, hp-boss is HpOff, the sieg loop
    (House0) runs HoldFullSend."""
    scada = h.child1_app.scada
    normal_handle = scada.layout.node(CoreNodeNames.local_control_normal).handle
    claimed = {
        name: relay
        for name, relay in relays.items()
        if scada.layout.node(name).handle == f"{normal_handle}.{name}"
    }
    assert set(energized) <= set(claimed)
    for name, relay in claimed.items():
        cfg = relay.relay_actor_config
        expected = cfg.EnergizedState if name in energized else cfg.DeEnergizedState
        assert relay.state == expected, f"{name}: {relay.state} != {expected}"
    outputs = [
        scada.services.get_communicator_as_type(node.Name, ZeroTenOutputer)
        for node in scada.layout.nodes.values()
        if node.ActorClass == ActorClass.ZeroTenOutputer
    ]
    assert outputs and all(outputs)
    for output in outputs:
        assert output.target_code == output.power_on_code
    hp_boss = scada.services.get_communicator_as_type(HSNN.hp_boss, HpBoss)
    assert hp_boss is not None
    assert hp_boss.state == HpBossState.HpOff
    sieg_loop = scada.services.get_communicator_as_type(House0NodeNames.sieg_loop, SiegLoop)
    if sieg_loop is not None:
        assert isinstance(sieg_loop.strategy, HoldFullSend)


async def assert_boot(
    request: pytest.FixtureRequest, layout_path: Path, ops_path: Path, row: Row
) -> None:
    layout = load_layout(layout_path, ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        scada = h.child1_app.scada
        lc = scada.services.get_communicator_as_type(CoreNodeNames.local_control, LocalControl)
        assert lc is not None
        assert type(lc._impl).__name__ == row.local_control.machine
        relays = {
            node.Name: scada.services.get_communicator_as_type(node.Name, Relay)
            for node in scada.layout.nodes.values()
            if node.ActorClass == ActorClass.Relay
        }
        assert relays and all(relays.values())

        def still_unknown() -> list[str]:
            return sorted(
                name for name, relay in relays.items() if relay.state == UNKNOWN_STATE
            )

        await h.await_for(
            lambda: not still_unknown(),
            "ERROR waiting for every relay to leave Unknown",
            timeout=10,
            err_str_f=lambda: f"still Unknown: {still_unknown()}",
        )
        if row.local_control.standby:
            hp_boss = scada.services.get_communicator_as_type(HSNN.hp_boss, HpBoss)
            assert hp_boss is not None
            await h.await_for(
                lambda: hp_boss.state == HpBossState.HpOff,
                "ERROR waiting for hp-boss to reach HpOff under standby",
                timeout=10,
            )
            assert_standby_posture(h, relays, lc.ops.EnergizedStandbyRelays)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    ROWS,
    ids=[f"{r.layout}-{r.local_control.machine}-{r.loop_strategy.value if r.loop_strategy else 'noloop'}" for r in ROWS],
)
async def test_every_relay_leaves_unknown_at_boot(
    request: pytest.FixtureRequest, tmp_path: Path, row: Row
) -> None:
    layout_file, ops_file = LAYOUTS[row.layout]
    await assert_boot(request, CONFIG / layout_file, row_ops(tmp_path, ops_file, row), row)


STANDBY_ROWS = tuple(row for row in ROWS if row.local_control.standby)


def admin_dispatch(to_name: str, event_type: str, event_name: str) -> AdminDispatch:
    """The admin client's wire shape for a state command to one node."""
    return AdminDispatch(
        DispatchTrigger=FsmEvent(
            FromHandle=CoreNodeNames.admin,
            ToHandle=f"{CoreNodeNames.admin}.{to_name}",
            EventType=event_type,
            EventName=event_name,
            SendTimeUnixMs=int(time.time() * 1000),
            TriggerId=str(uuid.uuid4()),
        ),
        TimeoutSeconds=120,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row", STANDBY_ROWS, ids=[f"{r.layout}-{r.local_control.machine}" for r in STANDBY_ROWS]
)
async def test_standby_posture_restored_after_admin(
    request: pytest.FixtureRequest, tmp_path: Path, row: Row
) -> None:
    """Standby boots to its posture; admin takes the tree, turns the heat
    pump on and energizes a relay the ops word does not list; on release
    the posture is back and hp-boss is HpOff again."""
    layout_file, ops_file = LAYOUTS[row.layout]
    ops_path = row_ops(tmp_path, ops_file, row)
    layout = load_layout(CONFIG / layout_file, ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        scada = h.child1_app.scada
        lc = scada.services.get_communicator_as_type(CoreNodeNames.local_control, LocalControl)
        assert lc is not None
        energized = lc.ops.EnergizedStandbyRelays
        relays = {
            node.Name: scada.services.get_communicator_as_type(node.Name, Relay)
            for node in scada.layout.nodes.values()
            if node.ActorClass == ActorClass.Relay
        }
        hp_boss = scada.services.get_communicator_as_type(HSNN.hp_boss, HpBoss)
        assert hp_boss is not None
        await h.await_for(
            lambda: all(relay.state != UNKNOWN_STATE for relay in relays.values())
            and hp_boss.state == HpBossState.HpOff,
            "ERROR waiting for the standby posture at boot",
            timeout=10,
        )
        assert_standby_posture(h, relays, energized)
        normal_handle = scada.layout.node(CoreNodeNames.local_control_normal).handle
        disturbed_name = next(
            name
            for name in sorted(relays)
            if scada.layout.node(name).handle == f"{normal_handle}.{name}" and name not in energized
        )
        disturbed = relays[disturbed_name]
        cfg = disturbed.relay_actor_config

        scada.process_scada_message(
            scada.admin, admin_dispatch(HSNN.hp_boss, TurnHpOnOff.enum_name(), TurnHpOnOff.TurnOn)
        )
        assert scada.top_state == TopState.Admin
        assert lc.top_state == LocalControlStandbyTopState.Dormant
        await h.await_for(
            lambda: hp_boss.state == HpBossState.HpOn,
            "ERROR waiting for admin's TurnOn to reach HpOn",
        )
        scada.process_scada_message(
            scada.admin, admin_dispatch(disturbed_name, cfg.EventType, cfg.EnergizingEvent)
        )
        await h.await_for(
            lambda: disturbed.state == cfg.EnergizedState,
            f"ERROR waiting for admin to energize {disturbed_name}",
        )

        scada.process_scada_message(scada.admin, AdminReleaseControl())
        assert scada.top_state == TopState.Auto
        assert lc.top_state == LocalControlStandbyTopState.EverythingOff
        await h.await_for(
            lambda: hp_boss.state == HpBossState.HpOff and disturbed.state == cfg.DeEnergizedState,
            "ERROR waiting for the standby posture to be restored after admin's release",
            timeout=10,
        )
        assert_standby_posture(h, relays, energized)
