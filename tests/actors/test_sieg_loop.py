"""sieg-loop, the Siegenthaler valve actor on both House0 fixtures: the
strategy the ops word selects, a valve movement reaching the two relays it
drives (keep/send direction, then the on/off that starts the motion) under
the sieg-loop's own handle, the valve travel timed on the scada's clock, and
the valve state reported on change. Guards the partition residue where the
actor lost its choreography and the movement error was swallowed, so the
valve silently never moved."""

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest

from actors.hydronic.house0 import House0Hydronic
from actors.sieg_loop import (
    HoldFullSend,
    SiegControlState,
    SiegLoop,
    SiegLoopReady,
    SiegValveEvent,
    SiegValveState,
    StratProtect,
)
from clock import ManualClock
from gwproto import Message
from gwproto.message import Header
from gwsproto.enums import (
    ActuationAuthority,
    ChangeKeepSend,
    ChangeRelayState,
    HpBossState,
    MainAutoEvent,
    MoveSiegValve,
    ScadaCmdRefusalReason,
    SiegLoopStrategy,
    TurnHpOnOff,
)
from gwsproto.named_types import (
    ActuatorsReady,
    DispatchAck,
    DispatchNack,
    FsmEvent,
    FsmFullReport,
    SingleMachineState,
)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from gwsproto.names.house0.node_names import House0NodeNames
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
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


def sieg_loop_actor(app: ScadaApp) -> SiegLoop:
    actor = app.get_communicator_as_type(House0NodeNames.sieg_loop, SiegLoop)
    assert actor is not None, "sieg-loop is constructed in every House0 layout"
    return actor


def capture(actor: SiegLoop) -> list:
    sent: list = []
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    actor._send = lambda message: None  # the watchdog pat on the tick
    return sent


def test_sieg_loop_carries_the_valve_choreography(app: ScadaApp) -> None:
    actor = sieg_loop_actor(app)
    assert isinstance(actor, House0Hydronic)
    assert actor.hp_boss.name == HSNN.hp_boss


@pytest.mark.parametrize(
    ("valve_event", "direction"),
    [
        (SiegValveEvent.StartKeepingMore, ChangeKeepSend.ChangeToKeepMore),
        (SiegValveEvent.StartKeepingLess, ChangeKeepSend.ChangeToKeepLess),
    ],
)
def test_valve_movement_reaches_both_relays(
    app: ScadaApp, valve_event: SiegValveEvent, direction: ChangeKeepSend
) -> None:
    """A keep-more or keep-less movement sends the direction to the keep/send
    relay and then closes the on/off relay, both from the sieg-loop's handle
    (the relays sit under it in the command tree)."""
    actor = sieg_loop_actor(app)
    sent = capture(actor)
    start = (
        SiegValveState.FullySend
        if valve_event == SiegValveEvent.StartKeepingMore
        else SiegValveState.FullyKeep
    )
    actor.valve.valve_state = start
    actor.valve.trigger_valve_event(valve_event)

    commands = [(name, p) for name, p in sent if isinstance(p, FsmEvent)]
    assert [name for name, _ in commands] == [House0NodeNames.hp_loop_keep_send, House0NodeNames.hp_loop_on_off]
    keep_send, on_off = (payload for _, payload in commands)
    assert isinstance(keep_send, FsmEvent)
    assert keep_send.EventType == ChangeKeepSend.enum_name()
    assert keep_send.EventName == direction
    assert keep_send.FromHandle == actor.node.handle
    assert isinstance(on_off, FsmEvent)
    assert on_off.EventType == ChangeRelayState.enum_name()
    assert on_off.EventName == ChangeRelayState.CloseRelay
    assert on_off.FromHandle == actor.node.handle
    assert actor.valve.valve_state != start


LOOP_RELAYS = (House0NodeNames.hp_loop_on_off, House0NodeNames.hp_loop_keep_send)
LOOP_METHODS = ("sieg_valve_active", "sieg_valve_hold", "change_to_hp_keep_more", "change_to_hp_keep_less")


def test_loop_relays_hang_under_sieg_loop_in_every_tree(app: ScadaApp) -> None:
    """sieg-loop is the immediate boss of relays 14 and 15 whichever node
    holds the tree: local control's normal node, admin, or local control
    itself when the scada rebuilds the tree. A tree rewrite reparents
    sieg-loop and never reaches through it to its relays."""
    scada = app.scada
    scada._send_to = lambda dst, payload, src=None: None
    layout = scada.layout
    loop = layout.node(House0NodeNames.sieg_loop)

    def relays_hang_under_the_loop() -> None:
        for name in LOOP_RELAYS:
            assert layout.node(name).handle == f"{loop.handle}.{name}"

    assert loop.handle == f"{CoreNodeNames.auto}.{CoreNodeNames.local_control}.{CoreNodeNames.local_control_normal}.{House0NodeNames.sieg_loop}"
    relays_hang_under_the_loop()
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    assert loop.handle == f"{CoreNodeNames.admin}.{House0NodeNames.sieg_loop}"
    relays_hang_under_the_loop()
    scada.auto_trigger(MainAutoEvent.AutoWakesUp)
    assert loop.handle == f"{CoreNodeNames.auto}.{CoreNodeNames.local_control}.{House0NodeNames.sieg_loop}"
    relays_hang_under_the_loop()


def test_a_boss_side_command_to_a_loop_relay_fails_the_event_axiom(app: ScadaApp) -> None:
    """The ownership is enforced at the event: fsm.event axiom 2 makes the
    sender the relay's immediate boss, and that is sieg-loop, so a boss
    node cannot even build a command to relay 14 or 15."""
    layout = app.scada.layout
    boss = layout.node(CoreNodeNames.local_control_normal)
    for name in LOOP_RELAYS:
        with pytest.raises(ValueError, match="immediate boss"):
            FsmEvent(
                FromHandle=boss.handle,
                ToHandle=layout.node(name).handle,
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )


@pytest.mark.parametrize("boss_name", [CoreNodeNames.local_control, CoreNodeNames.leaf_ally])
def test_boss_nodes_leave_the_loop_relays_alone_at_initialization(
    app: ScadaApp, boss_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local control and the leaf ally set every relay they own at
    initialization and touch neither loop relay, by any of the four loop
    methods: sieg-loop parks its own motor."""
    scada = app.scada
    scada._send_to = lambda dst, payload, src=None: None
    boss = scada.get_communicator(boss_name)
    if boss_name == CoreNodeNames.leaf_ally:
        scada.set_command_tree(boss.node)  # local control's normal node holds the tree from instantiation
    impl = getattr(boss, "_impl", boss)
    assert isinstance(impl, House0Hydronic)
    sent: list = []
    impl._send_to = lambda dst, payload, src=None: sent.append(dst.name)
    called: list[str] = []
    for method in LOOP_METHODS:
        monkeypatch.setattr(impl, method, lambda *a, _m=method, **k: called.append(_m))
    impl.actuators_ready = True
    impl.initialize_actuators()

    assert sent, "initialization sets the relays the boss owns"
    assert called == []
    assert not set(sent) & set(LOOP_RELAYS)


# --- the strategy and the clock ---------------------------------------------


def manual_app(
    tmp_path: Path,
    pair: str = "house0-willow",
    strategy: SiegLoopStrategy | None = None,
    authority: ActuationAuthority | None = None,
) -> tuple[ScadaApp, ManualClock]:
    """The fixture pair on a manual clock, with the ops word's strategy or
    actuation authority overridden."""
    layout, ops = PAIRS[pair]
    ops_dict = json.loads((CONFIG / ops).read_text())
    if strategy is not None:
        ops_dict["FamilyParams"]["SiegLoopStrategy"] = strategy.value
    if authority is not None:
        ops_dict["ActuationAuthority"] = authority.value
    ops_path = tmp_path / ops
    ops_path.write_text(json.dumps(ops_dict))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = ops_path
    settings.paths.mkdirs()
    clock = ManualClock(start_s=1_700_000_000)
    scada_app = ScadaApp(app_settings=settings, clock=clock)
    scada_app.instantiate()
    return scada_app, clock


def deliver(actor: SiegLoop, src: str, payload) -> None:
    actor.process_message(
        Message(
            header=Header(Src=src, Dst=actor.name, MessageType=payload.TypeName),
            Payload=payload,
        )
    )


def hp_boss_state(actor: SiegLoop, state: HpBossState) -> SingleMachineState:
    return SingleMachineState(
        MachineHandle=actor.hp_boss.handle,
        StateEnum=HpBossState.enum_name(),
        State=state,
        UnixMs=int(time.time() * 1000),
    )


def relay_events(sent: list) -> list[tuple[str, str]]:
    """(ToName, EventName) of every relay command sent."""
    return [(dst, p.EventName) for dst, p in sent if isinstance(p, FsmEvent)]


def valve_reports(sent: list) -> list[str]:
    return [
        p.State
        for _, p in sent
        if isinstance(p, SingleMachineState) and p.StateEnum == SiegValveState.enum_name()
    ]


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


TO_SEND = [
    (House0NodeNames.hp_loop_keep_send, ChangeKeepSend.ChangeToKeepLess),
    (House0NodeNames.hp_loop_on_off, ChangeRelayState.CloseRelay),
]
TO_KEEP = [
    (House0NodeNames.hp_loop_keep_send, ChangeKeepSend.ChangeToKeepMore),
    (House0NodeNames.hp_loop_on_off, ChangeRelayState.CloseRelay),
]
HOLD = [(House0NodeNames.hp_loop_on_off, ChangeRelayState.OpenRelay)]


def test_the_fixtures_run_strat_protect(app: ScadaApp) -> None:
    assert isinstance(sieg_loop_actor(app).strategy, StratProtect)


def test_standby_runs_hold_full_send_whatever_the_field_says(tmp_path: Path) -> None:
    app, _ = manual_app(tmp_path, strategy=SiegLoopStrategy.StratProtect, authority=ActuationAuthority.Standby)
    assert isinstance(sieg_loop_actor(app).strategy, HoldFullSend)


def test_lwt_control_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LwtControl"):
        manual_app(tmp_path, strategy=SiegLoopStrategy.LwtControl)


@pytest.mark.asyncio
async def test_hold_full_send_moves_once_to_send_then_only_answers(tmp_path: Path) -> None:
    """After ActuatorsReady one move to full send: direction to send, motor
    on for the full range plus the overshoot, motor off. Then nothing the
    heat pump does moves the valve, and hp-boss gets no ready message."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = sieg_loop_actor(app)
    sent = capture(actor)
    deliver(actor, actor.primary_scada.name, ActuatorsReady())
    await settle()
    assert relay_events(sent) == TO_SEND
    assert actor.valve.valve_state == SiegValveState.KeepingLess

    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S - 1)
    await settle()
    assert relay_events(sent) == TO_SEND, "the motor runs the whole travel"
    clock.advance(1)
    await settle()
    assert relay_events(sent) == TO_SEND + HOLD
    assert actor.valve.keep_seconds == 0
    assert actor.valve.valve_state == SiegValveState.FullySend

    sent.clear()
    for state in (HpBossState.HpOff, HpBossState.PreparingToTurnOn, HpBossState.HpOn, HpBossState.HpOff):
        deliver(actor, actor.hp_boss.name, hp_boss_state(actor, state))
    actor.strategy.tick()
    await settle()
    assert relay_events(sent) == []
    assert not any(isinstance(p, SiegLoopReady) for _, p in sent)


@pytest.mark.asyncio
async def test_strat_protect_answers_preparing_to_turn_on_with_ready(app: ScadaApp) -> None:
    actor = sieg_loop_actor(app)
    sent = capture(actor)
    deliver(actor, actor.hp_boss.name, hp_boss_state(actor, HpBossState.PreparingToTurnOn))
    assert [dst for dst, p in sent if isinstance(p, SiegLoopReady)] == [actor.hp_boss.name]


@pytest.mark.asyncio
async def test_a_new_move_settles_the_travel_so_far_from_the_clock(tmp_path: Path) -> None:
    """A move toward send cut short by a move toward keep: the motor stops,
    keep_seconds is what the clock says ran, and the motor reverses from
    there. The finishing move clamps at full keep and lands on the stop."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = sieg_loop_actor(app)
    valve = actor.valve
    sent = capture(actor)
    assert valve.keep_seconds == valve.FULL_RANGE_S
    valve.move_to_full_send()
    await settle()
    clock.advance(40)
    await settle()
    assert valve.keep_seconds == valve.FULL_RANGE_S, "settled only when the motor stops"

    valve.move_to_full_keep()
    await settle()
    assert valve.keep_seconds == 60
    assert relay_events(sent) == TO_SEND + HOLD + TO_KEEP
    assert valve.valve_state == SiegValveState.KeepingMore

    clock.advance(60 + valve.OVERSHOOT_S)
    await settle()
    assert relay_events(sent) == TO_SEND + HOLD + TO_KEEP + HOLD
    assert valve.keep_seconds == valve.FULL_RANGE_S
    assert valve.valve_state == SiegValveState.FullyKeep


@pytest.mark.asyncio
async def test_one_valve_report_per_state_change(tmp_path: Path) -> None:
    """The valve state rides single.machine.state under sieg.valve.state, once
    per change and never between."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = sieg_loop_actor(app)
    sent = capture(actor)
    deliver(actor, actor.primary_scada.name, ActuatorsReady())
    await settle()
    for _ in range(3):
        actor.strategy.tick()
        clock.advance(10)
        await settle()
    assert valve_reports(sent) == [SiegValveState.KeepingLess]
    clock.advance(actor.valve.FULL_RANGE_S)
    await settle()
    assert valve_reports(sent) == [SiegValveState.KeepingLess, SiegValveState.FullySend]
    assert all(p.MachineHandle == actor.node.handle for _, p in sent if isinstance(p, SingleMachineState))


# --- the command surface -----------------------------------------------------


def move(actor: SiegLoop, name: MoveSiegValve, from_handle: str = CoreNodeNames.admin) -> FsmEvent:
    return FsmEvent(
        FromHandle=from_handle,
        ToHandle=actor.node.handle,
        EventType=MoveSiegValve.enum_name(),
        EventName=name,
        SendTimeUnixMs=int(time.time() * 1000),
        TriggerId=str(uuid.uuid4()),
    )


def loop_under_admin(app: ScadaApp) -> SiegLoop:
    scada = app.scada
    scada._send_to = lambda dst, payload, src=None: None
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    actor = sieg_loop_actor(app)
    assert actor.node.handle == f"{CoreNodeNames.admin}.{House0NodeNames.sieg_loop}"
    return actor


def replies(sent: list) -> list[tuple[str, type]]:
    return [(dst, type(p)) for dst, p in sent if isinstance(p, (DispatchAck, DispatchNack))]


@pytest.mark.asyncio
async def test_admin_move_is_acked_run_in_full_and_held_across_ticks(tmp_path: Path) -> None:
    """On HoldFullSend with the valve at full send, admin's MoveToFullKeep is
    acked, the motor runs the whole range plus the overshoot toward keep,
    the valve lands on FullyKeep, and ticks leave it there while admin holds
    the tree. The full report carries the commander's TriggerId."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = loop_under_admin(app)
    sent = capture(actor)
    deliver(actor, actor.primary_scada.name, ActuatorsReady())
    await settle()
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S)
    await settle()
    assert actor.valve.valve_state == SiegValveState.FullySend
    sent.clear()

    cmd = move(actor, MoveSiegValve.MoveToFullKeep)
    deliver(actor, CoreNodeNames.admin, cmd)
    await settle()
    assert replies(sent) == [(CoreNodeNames.admin, DispatchAck)]
    assert relay_events(sent) == TO_KEEP
    assert not actor.automatic
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S - 1)
    await settle()
    assert relay_events(sent) == TO_KEEP, "a commanded move runs the full range whatever keep_seconds says"
    clock.advance(1)
    await settle()
    assert relay_events(sent) == TO_KEEP + HOLD
    assert actor.valve.valve_state == SiegValveState.FullyKeep
    [(dst, report)] = [(d, p) for d, p in sent if isinstance(p, FsmFullReport)]
    assert dst == actor.primary_scada.name
    assert report.TriggerId == cmd.TriggerId
    [atomic] = report.AtomicList
    assert (atomic.EventEnum, atomic.Event, atomic.FromState, atomic.ToState) == (
        MoveSiegValve.enum_name(), MoveSiegValve.MoveToFullKeep, SiegValveState.FullySend, SiegValveState.FullyKeep,
    )
    assert atomic.TriggerId == cmd.TriggerId

    sent.clear()
    for _ in range(3):
        actor.tick()
        clock.advance(actor.CONTROL_INTERVAL_S)
        await settle()
    assert relay_events(sent) == []
    assert actor.valve.valve_state == SiegValveState.FullyKeep


@pytest.mark.asyncio
async def test_a_commanded_move_holds_the_loop_until_the_tree_changes_hands(tmp_path: Path) -> None:
    """StratProtect with no readings is blind and wants full send; admin's
    MoveToFullKeep moves the valve to keep and the loop ignores its own
    control until the tree returns to local control, noticed on the tick,
    when it goes back to send."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.StratProtect)
    actor = loop_under_admin(app)
    sent = capture(actor)
    deliver(actor, actor.hp_boss.name, hp_boss_state(actor, HpBossState.HpOff))
    deliver(actor, actor.primary_scada.name, ActuatorsReady())
    await settle()
    assert isinstance(actor.strategy, StratProtect)
    assert actor.strategy.control_state == SiegControlState.Blind
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S)
    await settle()
    assert actor.valve.valve_state == SiegValveState.FullySend
    sent.clear()

    deliver(actor, CoreNodeNames.admin, move(actor, MoveSiegValve.MoveToFullKeep))
    await settle()
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S)
    await settle()
    assert actor.valve.valve_state == SiegValveState.FullyKeep
    sent.clear()
    deliver(actor, actor.hp_boss.name, hp_boss_state(actor, HpBossState.HpOn))
    deliver(actor, actor.hp_boss.name, hp_boss_state(actor, HpBossState.HpOff))
    actor.tick()
    await settle()
    assert relay_events(sent) == [], "the strategy's moves are withheld while admin's command holds"
    assert actor.valve.valve_state == SiegValveState.FullyKeep

    app.scada.auto_trigger(MainAutoEvent.AutoWakesUp)
    assert actor.node.handle.startswith(CoreNodeNames.auto)
    actor.tick()
    await settle()
    assert actor.automatic
    assert relay_events(sent) == TO_SEND
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S)
    await settle()
    assert actor.valve.valve_state == SiegValveState.FullySend


@pytest.mark.asyncio
async def test_bad_commands_move_nothing(tmp_path: Path) -> None:
    """A command whose FromHandle is not the sender's is dropped; one to a
    stale handle is nacked NotMyBoss; a wrong EventType is nacked
    UnknownEvent. None moves the valve or holds the loop."""
    app, _ = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = loop_under_admin(app)
    sent = capture(actor)

    deliver(actor, CoreNodeNames.local_control, move(actor, MoveSiegValve.MoveToFullKeep))
    assert replies(sent) == [], "dropped with a warning, no reply"

    stale = move(actor, MoveSiegValve.MoveToFullKeep)
    stale = stale.model_copy(update={"ToHandle": f"auto.lc.n.{House0NodeNames.sieg_loop}"})
    deliver(actor, CoreNodeNames.admin, stale)
    [(dst, nack)] = [(d, p) for d, p in sent if isinstance(p, DispatchNack)]
    assert (dst, nack.Reason) == (CoreNodeNames.admin, ScadaCmdRefusalReason.NotMyBoss)
    sent.clear()

    wrong = move(actor, MoveSiegValve.MoveToFullKeep).model_copy(
        update={"EventType": TurnHpOnOff.enum_name(), "EventName": TurnHpOnOff.TurnOn}
    )
    deliver(actor, CoreNodeNames.admin, wrong)
    [(dst, nack)] = [(d, p) for d, p in sent if isinstance(p, DispatchNack)]
    assert (dst, nack.Reason) == (CoreNodeNames.admin, ScadaCmdRefusalReason.UnknownEvent)

    await settle()
    assert relay_events(sent) == []
    assert actor.automatic


def test_capabilities_cover_sieg_loop_with_its_two_moves(app: ScadaApp) -> None:
    """The panel commands sieg-loop with move.sieg.valve; relays 14 and 15
    sit under it and are commanded through it."""
    caps = app.scada.control_capabilities
    by_actor: dict[str, list] = {}
    for i in caps.CommandInterfaces:
        by_actor.setdefault(i.ActorName, []).append(i)
    [interface] = by_actor[House0NodeNames.sieg_loop]
    assert interface.EventType == MoveSiegValve.enum_name()
    assert interface.StateType == SiegValveState.enum_name()
    assert {(c.Event, c.ToState) for c in interface.Commands} == {
        (MoveSiegValve.MoveToFullSend, SiegValveState.FullySend),
        (MoveSiegValve.MoveToFullKeep, SiegValveState.FullyKeep),
    }
    assert House0NodeNames.hp_loop_on_off not in by_actor
    assert House0NodeNames.hp_loop_keep_send not in by_actor
    assert House0NodeNames.sieg_loop in {n.Name for n in caps.CommandNodes}
