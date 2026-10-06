"""The command tree after each top-state transition of each local
control, on the authored pairs: the whole tree has the shape the state
calls for, the tree the local control publishes is that tree, and no
command sent in the transition was dropped for want of the rights."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from gwproto.message import Message

from actors.local_control.house0.tou_base import LocalControlTouBase
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control.standby import StandbyLocalControl
from actors.local_control_loader import LocalControl
from actors.scada import Scada
from gwsproto.enums import DispatchRefusalReason, LocalControlTopState, MainAutoEvent
from gwsproto.named_types import GoDormant, NewCommandTree, WakeUp
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp
from tests.actors.test_cold_handling import CONFIG, NOLAN, WILLOW, heating_ops, make_app, put_f

ORANGE = ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json")
HOUSE0 = {"willow": WILLOW, "orange": ORANGE}
EVERY_PAIR = {**HOUSE0, "nolan": NOLAN}

Impl = LocalControlTouBase | NolanBufferOnlyTou | StandbyLocalControl


class Seen:
    """What a local control published and logged, its sends kept from the
    actors they were addressed to."""

    def __init__(self, impl: Impl) -> None:
        self.trees: list[dict[str, str]] = []
        self.logs: list[str] = []

        def record(dst, payload, src=None) -> None:
            if isinstance(payload, NewCommandTree):
                self.trees.append({n.Name: n.Handle or n.Name for n in payload.ShNodes})
                NewCommandTree.model_validate(
                    payload.model_dump(by_alias=True, exclude_none=True)
                )

        impl._send_to = record
        impl.log = self.logs.append


def impl_of(app: ScadaApp) -> Impl:
    lc = app.get_communicator_as_type(CoreNodeNames.local_control, LocalControl)
    assert lc is not None
    return lc._impl


def expected_handles(scada: Scada, boss_handle: str) -> dict[str, str]:
    """Every actuator and interior node of the tree whose boss has
    `boss_handle`: hp-boss and sieg-loop under the boss with their relays
    under them, the five-v-boss subtree under the root, and every other
    actuator a direct report of the boss."""
    layout = scada.layout
    root = boss_handle.split(".")[0]
    hp_boss = f"{boss_handle}.{layout.hp_boss.Name}"
    handles = {layout.hp_boss.Name: hp_boss}
    parents = {layout.hp_scada_ops_relay.Name: hp_boss}
    if layout.node(HSNN.five_v_boss) is not None:
        five_v_boss = f"{root}.{HSNN.five_v_boss}"
        cycler = f"{five_v_boss}.{HSNN.pico_cycler}"
        handles[HSNN.five_v_boss] = five_v_boss
        handles[HSNN.pico_cycler] = cycler
        parents[layout.vdc_relay.Name] = cycler
    if layout.node(House0NodeNames.sieg_loop) is not None:
        sieg_loop = f"{boss_handle}.{House0NodeNames.sieg_loop}"
        handles[House0NodeNames.sieg_loop] = sieg_loop
        for name in (House0NodeNames.hp_loop_on_off, House0NodeNames.hp_loop_keep_send):
            parents[name] = sieg_loop
    for node in layout.actuators:
        handles[node.Name] = f"{parents.get(node.Name, boss_handle)}.{node.Name}"
    return handles


def assert_tree(scada: Scada, seen: Seen, boss_handle: str, published: bool = True) -> None:
    expected = expected_handles(scada, boss_handle)
    live = {name: scada.layout.node(name).handle for name in expected}
    assert live == expected
    if published:
        assert seen.trees, "the transition published no tree"
        assert {name: seen.trees[-1][name] for name in expected} == expected
    assert not [line for line in seen.logs if "rights" in line]


def state_node_handle(scada: Scada, name: str) -> str:
    return scada.layout.node(name).handle


def scada_tells(scada: Scada, impl: Impl, trigger: MainAutoEvent) -> None:
    """Pull an auto trigger on the scada and hand the local control the
    GoDormant or WakeUp the scada addresses to it."""
    to_lc: list[Any] = []

    def record(dst, payload, src=None) -> None:
        if dst.name == CoreNodeNames.local_control and isinstance(payload, (GoDormant, WakeUp)):
            to_lc.append(payload)

    scada._send_to = record
    scada.auto_trigger(trigger)
    assert len(to_lc) == 1
    impl.process_message(
        Message(Src=scada.name, Dst=CoreNodeNames.local_control, Payload=to_lc[0])
    )


@pytest.fixture(params=sorted(HOUSE0))
def house0(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[Scada, LocalControlTouBase, Seen]:
    app = make_app(HOUSE0[request.param], heating_ops(tmp_path, HOUSE0[request.param]))
    impl = impl_of(app)
    assert isinstance(impl, LocalControlTouBase)
    return app.scada, impl, Seen(impl)


@pytest.fixture
def nolan(tmp_path: Path) -> tuple[Scada, NolanBufferOnlyTou, Seen]:
    app = make_app(NOLAN, heating_ops(tmp_path, NOLAN))
    impl = impl_of(app)
    assert isinstance(impl, NolanBufferOnlyTou)
    seen = Seen(impl)
    impl.on_actuators_ready()
    return app.scada, impl, seen


@pytest.fixture(params=sorted(EVERY_PAIR))
def heating(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[Scada, Impl, Seen]:
    pair = EVERY_PAIR[request.param]
    app = make_app(pair, heating_ops(tmp_path, pair))
    impl = impl_of(app)
    return app.scada, impl, Seen(impl)


@pytest.fixture(params=sorted(EVERY_PAIR))
def standby(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[Scada, Impl, Seen]:
    pair = EVERY_PAIR[request.param]
    ops_path = heating_ops(
        tmp_path,
        pair,
        Standby=True,
        AcceptsDispatch=False,
        DispatchRefusalReason=DispatchRefusalReason.Standby.value,
    )
    app = make_app(pair, ops_path)
    impl = impl_of(app)
    assert isinstance(impl, StandbyLocalControl)
    return app.scada, impl, Seen(impl)


def test_a_heating_local_control_boots_holding_the_tree_from_n(
    heating: tuple[Scada, Impl, Seen],
) -> None:
    scada, impl, seen = heating
    assert impl.top_state == LocalControlTopState.Normal
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_normal), published=False)


def test_house0_system_cold_moves_the_tree_under_backup_and_warm_moves_it_back(
    house0: tuple[Scada, LocalControlTouBase, Seen],
) -> None:
    scada, impl, seen = house0
    impl.trigger_system_cold_event()
    assert impl.top_state == LocalControlTopState.InBackup
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_backup))
    impl.trigger_zones_at_setpoint_offpeak()
    assert impl.top_state == LocalControlTopState.Normal
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_normal))


@pytest.mark.parametrize("house", sorted(HOUSE0))
def test_house0_system_cold_without_backup_moves_the_tree_under_cold_override_and_warm_moves_it_back(
    house: str, tmp_path: Path,
) -> None:
    pair = HOUSE0[house]
    app = make_app(pair, heating_ops(tmp_path, pair, UsesBackupWhenCold=False))
    impl = impl_of(app)
    assert isinstance(impl, LocalControlTouBase)
    scada, seen = app.scada, Seen(impl)
    impl.trigger_system_cold_event()
    assert impl.top_state == LocalControlTopState.ColdOverride
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_cold_override))
    impl.trigger_zones_at_setpoint_offpeak()
    assert impl.top_state == LocalControlTopState.Normal
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_normal))


def test_a_house0_house_with_no_backup_boots_and_goes_to_cold_override(tmp_path: Path) -> None:
    layout = json.loads((CONFIG / WILLOW[0]).read_text())
    del layout["Hydronic"]["Backup"]
    layout["ShNodes"] = [n for n in layout["ShNodes"] if n["Name"] != CoreNodeNames.local_control_backup]
    layout_path = tmp_path / "hardware-layout.json"
    layout_path.write_text(json.dumps(layout, indent=2))
    pair = (str(layout_path), WILLOW[1])
    app = make_app(pair, heating_ops(tmp_path, pair, UsesBackupWhenCold=False))
    impl = impl_of(app)
    assert isinstance(impl, LocalControlTouBase)
    scada, seen = app.scada, Seen(impl)
    impl.trigger_system_cold_event()
    assert impl.top_state == LocalControlTopState.ColdOverride
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_cold_override))


def test_house0_missing_data_moves_the_tree_under_scada_blind_and_data_moves_it_back(
    house0: tuple[Scada, LocalControlTouBase, Seen],
) -> None:
    scada, impl, seen = house0
    impl.trigger_missing_data()
    assert impl.top_state == LocalControlTopState.ScadaBlind
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_scada_blind))
    impl.trigger_data_available()
    assert impl.top_state == LocalControlTopState.Normal
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_normal))


def test_nolan_a_blind_band_moves_the_tree_under_scada_blind_and_a_fresh_one_moves_it_back(
    nolan: tuple[Scada, NolanBufferOnlyTou, Seen],
) -> None:
    scada, impl, seen = nolan
    now = datetime.now(tz=timezone.utc)
    impl.check(now)
    assert impl.top_state == LocalControlTopState.ScadaBlind
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_scada_blind))
    for channel in (HCN.buffer.depth1, HCN.buffer.depth3):
        put_f(impl, channel, 120)
        impl.data.latest_channel_unix_ms[channel] = int(time.time() * 1000)
    impl.check(now)
    assert impl.top_state == LocalControlTopState.Normal
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_normal))


def test_admin_taking_the_tree_leaves_a_heating_local_control_dormant_and_its_release_wakes_it(
    heating: tuple[Scada, Impl, Seen],
) -> None:
    scada, impl, seen = heating
    scada_tells(scada, impl, MainAutoEvent.AutoGoesDormant)
    assert impl.top_state == LocalControlTopState.Dormant
    assert impl.my_actuators() == []
    assert_tree(scada, seen, CoreNodeNames.admin, published=False)
    scada_tells(scada, impl, MainAutoEvent.AutoWakesUp)
    assert impl.top_state == LocalControlTopState.Normal
    assert_tree(scada, seen, state_node_handle(scada, CoreNodeNames.local_control_normal))


def test_a_standby_local_control_holds_the_tree_from_standby_through_admin_and_back(
    standby: tuple[Scada, Impl, Seen],
) -> None:
    scada, impl, seen = standby
    standby_handle = state_node_handle(scada, CoreNodeNames.local_control_standby)
    assert impl.top_state == LocalControlTopState.Standby
    assert_tree(scada, seen, standby_handle, published=False)
    scada_tells(scada, impl, MainAutoEvent.AutoGoesDormant)
    assert impl.top_state == LocalControlTopState.Dormant
    assert impl.my_actuators() == []
    assert_tree(scada, seen, CoreNodeNames.admin, published=False)
    scada_tells(scada, impl, MainAutoEvent.AutoWakesUp)
    assert impl.top_state == LocalControlTopState.Standby
    assert_tree(scada, seen, standby_handle)
