"""Every node that is the direct boss of an actuator boots its actuators:
once the actuators are ready, every relay in the layout leaves Unknown
within seconds of the scada starting, under every local-control strategy
and every sieg-loop strategy.

The rows are an each-choice covering (a 1-wise covering array), not the
product of the axes: every value of every axis appears in at least one
row, so the row count is the size of the largest axis, and adding a value
to an axis adds one row rather than multiplying them. The axes are
independent except for one constraint the ops word imposes: Standby runs
HoldFullSend whatever the field says (`actors/sieg_loop/strategy.py`
`selected_strategy`), so the Standby row carries HoldFullSend.
`test_rows_cover_every_axis_value` fails when an axis grows without a
row covering the new value."""

import json
from pathlib import Path
from typing import NamedTuple

import pytest

from actors.relay import Relay, UNKNOWN_STATE
from gwsproto.enums import ActorClass, ActuationAuthority, SeasonalStorageMode, SiegLoopStrategy
from sema_to_dc import load_layout
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
WILLOW = ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")
ORANGE = ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json")
NOLAN = ("gw.nolan.layout.json", "gw.nolan.operational.params.json")


class LocalControlChoice(NamedTuple):
    """One local-control strategy as the ops word selects it
    (`actors/local_control_loader.py`): the authority and storage mode
    that load the controller."""

    controller: str
    authority: ActuationAuthority
    storage: SeasonalStorageMode


# Axis 1: every House0 local-control strategy the loader can pick.
LOCAL_CONTROLS = (
    LocalControlChoice("AllTanksTou", ActuationAuthority.Active, SeasonalStorageMode.AllTanks),
    LocalControlChoice("BufferOnlyTou", ActuationAuthority.Active, SeasonalStorageMode.BufferOnly),
    LocalControlChoice("Standby", ActuationAuthority.Standby, SeasonalStorageMode.AllTanks),
)
# Axis 2: every sieg-loop strategy the loop constructs (`actors/sieg_loop`).
LOOP_STRATEGIES = (SiegLoopStrategy.HoldFullSend, SiegLoopStrategy.StratProtect)
# Axis 3: every House0 test layout.
LAYOUTS = {"willow": WILLOW, "orange": ORANGE}


class Row(NamedTuple):
    """One boot to run: a House0 layout under one local-control strategy
    and one sieg-loop strategy."""

    layout: str
    local_control: LocalControlChoice
    loop_strategy: SiegLoopStrategy


ROWS = (
    Row("willow", LOCAL_CONTROLS[0], SiegLoopStrategy.StratProtect),
    Row("orange", LOCAL_CONTROLS[1], SiegLoopStrategy.HoldFullSend),
    Row("willow", LOCAL_CONTROLS[2], SiegLoopStrategy.HoldFullSend),  # Standby forces HoldFullSend
)


def test_rows_cover_every_axis_value() -> None:
    assert {row.local_control for row in ROWS} == set(LOCAL_CONTROLS)
    assert {row.loop_strategy for row in ROWS} == set(LOOP_STRATEGIES)
    assert {row.layout for row in ROWS} == set(LAYOUTS)
    for row in ROWS:
        if row.local_control.authority is ActuationAuthority.Standby:
            assert row.loop_strategy is SiegLoopStrategy.HoldFullSend


def house0_ops(tmp_path: Path, ops_file: str, row: Row) -> Path:
    """The layout's ops artifact with the row's strategy selection."""
    ops = json.loads((CONFIG / ops_file).read_text())
    ops["ActuationAuthority"] = row.local_control.authority.value
    ops["FamilyParams"]["SeasonalStorageMode"] = row.local_control.storage.value
    ops["FamilyParams"]["SiegLoopStrategy"] = row.loop_strategy.value
    path = tmp_path / ops_file
    path.write_text(json.dumps(ops))
    return path


async def assert_every_relay_leaves_unknown(
    request: pytest.FixtureRequest, layout_path: Path, ops_path: Path
) -> None:
    layout = load_layout(layout_path, ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        scada = h.child1_app.scada
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row", ROWS, ids=[f"{r.layout}-{r.local_control.controller}-{r.loop_strategy.value}" for r in ROWS]
)
async def test_every_house0_relay_leaves_unknown_at_boot(
    request: pytest.FixtureRequest, tmp_path: Path, row: Row
) -> None:
    layout_file, ops_file = LAYOUTS[row.layout]
    await assert_every_relay_leaves_unknown(
        request, CONFIG / layout_file, house0_ops(tmp_path, ops_file, row)
    )


@pytest.mark.asyncio
async def test_every_nolan_relay_leaves_unknown_at_boot(
    request: pytest.FixtureRequest,
) -> None:
    layout_file, ops_file = NOLAN
    await assert_every_relay_leaves_unknown(request, CONFIG / layout_file, CONFIG / ops_file)
