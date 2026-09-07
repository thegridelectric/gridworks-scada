"""hp-boss, the heat pump's command node, in every layout: its place in every
command tree, both strategies (sieg: TurnOn waits on SiegLoopReady; sieg-less:
TurnOn closes the call relay now), a stale boss changing nothing, and admin
turning the heat pump on and off through hp-boss rather than by addressing the
relay itself."""

import time
import uuid
from pathlib import Path

import pytest

from actors.hp_boss import HpBoss, SiegLoopReady
from gwproto import Message
from gwproto.message import Header
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import ChangeRelayState, HpBossState, TurnHpOnOff
from gwsproto.named_types import (
    AdminDispatch,
    FsmEvent,
    SingleMachineState,
)
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
    "house0-sim": (
        "gw.house0.sim.layout.json",
        "gw.house0.sim.operational.params.json",
    ),
}


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def capture(actor) -> list:
    sent: list = []
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def hp_boss_actor(app: ScadaApp) -> HpBoss:
    actor = app.get_communicator_as_type(H0N.hp_boss, HpBoss)
    assert actor is not None, "hp-boss actor is constructed in every layout"
    return actor


def turn(from_handle: str, to_handle: str, name: TurnHpOnOff) -> FsmEvent:
    return FsmEvent(
        FromHandle=from_handle,
        ToHandle=to_handle,
        EventType=TurnHpOnOff.enum_name(),
        EventName=name,
        SendTimeUnixMs=int(time.time() * 1000),
        TriggerId=str(uuid.uuid4()),
    )


def deliver(actor: HpBoss, src: str, payload) -> None:
    actor.process_message(
        Message(
            header=Header(Src=src, Dst=actor.name, MessageType=payload.TypeName),
            Payload=payload,
        )
    )


def relay_events(sent: list) -> list[tuple[str, str, str]]:
    """(FromHandle, ToHandle, EventName) of every relay command sent."""
    return [
        (p.FromHandle, p.ToHandle, p.EventName)
        for _, p in sent
        if isinstance(p, FsmEvent) and p.EventType == ChangeRelayState.enum_name()
    ]


def reported_states(sent: list) -> list[str]:
    return [p.State for _, p in sent if isinstance(p, SingleMachineState)]


@pytest.mark.parametrize("boss", ["admin", "local_control", "leaf_ally"])
def test_hp_boss_in_every_tree(app: ScadaApp, boss: str) -> None:
    """Whatever boss the scada hands the tree to, hp-boss sits directly under
    it and the call relay reports to hp-boss; the loop pair rides only when
    the ops word runs the loop."""
    scada = app.scada
    capture(scada)
    boss_node = getattr(scada, boss)
    scada.set_command_tree(boss_node)
    hp_boss = scada.layout.hp_boss
    relay = scada.layout.hp_scada_ops_relay
    assert hp_boss.handle == f"{boss_node.handle}.{H0N.hp_boss}"
    assert relay.handle == f"{hp_boss.handle}.{H0N.hp_scada_ops_relay}"
    sieg_loop = scada.layout.node(H0N.sieg_loop, None)
    if scada.data.use_sieg_loop:
        assert sieg_loop is not None
        assert sieg_loop.handle == f"{boss_node.handle}.{H0N.sieg_loop}"
        for name in (H0N.hp_loop_on_off, H0N.hp_loop_keep_send):
            assert scada.layout.node(name).handle == f"{sieg_loop.handle}.{name}"
    assert scada.hp_boss is hp_boss


def test_turn_off_opens_call_relay_from_hp_boss(app: ScadaApp) -> None:
    scada = app.scada
    capture(scada)
    scada.set_command_tree(scada.local_control)
    actor = hp_boss_actor(app)
    sent = capture(actor)
    boss = scada.local_control
    deliver(actor, boss.name, turn(boss.handle, actor.node.handle, TurnHpOnOff.TurnOff))
    relay = scada.layout.hp_scada_ops_relay
    assert relay_events(sent) == [
        (actor.node.handle, relay.handle, ChangeRelayState.OpenRelay)
    ]
    assert actor.state == HpBossState.HpOff
    assert reported_states(sent) == [HpBossState.HpOff]


@pytest.mark.asyncio
async def test_turn_on_follows_the_layout_strategy(app: ScadaApp) -> None:
    """Sieg-less: TurnOn closes the call relay now and reports HpOn. Sieg:
    TurnOn reports PreparingToTurnOn and the relay closes only when the
    loop says ready."""
    scada = app.scada
    capture(scada)
    scada.set_command_tree(scada.local_control)
    actor = hp_boss_actor(app)
    actor.state = HpBossState.HpOff
    sent = capture(actor)
    boss = scada.local_control
    relay = scada.layout.hp_scada_ops_relay
    deliver(actor, boss.name, turn(boss.handle, actor.node.handle, TurnHpOnOff.TurnOn))
    close = (actor.node.handle, relay.handle, ChangeRelayState.CloseRelay)
    if scada.data.use_sieg_loop:
        assert relay_events(sent) == []
        assert actor.state == HpBossState.PreparingToTurnOn
        assert reported_states(sent) == [HpBossState.PreparingToTurnOn]
        deliver(actor, H0N.sieg_loop, SiegLoopReady())
        assert relay_events(sent) == [close]
        assert actor.state == HpBossState.HpOn
        assert reported_states(sent) == [
            HpBossState.PreparingToTurnOn,
            HpBossState.HpOn,
        ]
    else:
        assert relay_events(sent) == [close]
        assert actor.state == HpBossState.HpOn
        assert reported_states(sent) == [HpBossState.HpOn]


def test_stale_boss_command_changes_nothing(app: ScadaApp) -> None:
    """The tree is under local-control; a well-formed command from admin
    (admin -> admin.hp-boss passes the FsmEvent axiom) is not addressed to
    hp-boss's current handle, so nothing moves and no state is reported."""
    scada = app.scada
    capture(scada)
    scada.set_command_tree(scada.local_control)
    actor = hp_boss_actor(app)
    actor.state = HpBossState.HpOn
    sent = capture(actor)
    stale = turn(H0N.admin, f"{H0N.admin}.{H0N.hp_boss}", TurnHpOnOff.TurnOff)
    deliver(actor, H0N.admin, stale)
    assert relay_events(sent) == []
    assert reported_states(sent) == []
    assert actor.state == HpBossState.HpOn


def admin_turn(name: TurnHpOnOff) -> AdminDispatch:
    """The admin client's wire shape: it addresses hp-boss under admin."""
    return AdminDispatch(
        DispatchTrigger=turn(H0N.admin, f"{H0N.admin}.{H0N.hp_boss}", name),
        TimeoutSeconds=120,
    )


@pytest.mark.asyncio
async def test_admin_turns_heat_pump_on_and_off_through_hp_boss(app: ScadaApp) -> None:
    """Admin wakes the scada, the tree moves under admin, and each dispatch
    reaches hp-boss itself, which commands the call relay at the relay's
    handle under admin.hp-boss."""
    scada = app.scada
    capture(scada)
    actor = hp_boss_actor(app)
    actor.state = HpBossState.HpOn
    sent = capture(actor)
    relay = scada.layout.hp_scada_ops_relay

    scada.process_admin_dispatch(scada.admin, admin_turn(TurnHpOnOff.TurnOff))
    hp_boss_handle = f"{H0N.admin}.{H0N.hp_boss}"
    assert actor.node.handle == hp_boss_handle
    assert relay.handle == f"{hp_boss_handle}.{H0N.hp_scada_ops_relay}"
    assert relay_events(sent) == [
        (hp_boss_handle, relay.handle, ChangeRelayState.OpenRelay)
    ]
    assert actor.state == HpBossState.HpOff

    sent.clear()
    scada.process_admin_dispatch(scada.admin, admin_turn(TurnHpOnOff.TurnOn))
    if scada.data.use_sieg_loop:
        assert actor.state == HpBossState.PreparingToTurnOn
        deliver(actor, H0N.sieg_loop, SiegLoopReady())
    assert relay_events(sent) == [
        (hp_boss_handle, relay.handle, ChangeRelayState.CloseRelay)
    ]
    assert actor.state == HpBossState.HpOn
    scada.admin_times_out()
