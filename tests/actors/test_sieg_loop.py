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
from actors.in_process_messages import MachineStateSubscribe
from actors.sieg_loop import (
    VIEW_CHANNELS,
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
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwproto.message import Header
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ChangeKeepSend,
    ChangeRelayState,
    FsmReportType,
    HpBossState,
    LogLevel,
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
    FsmAtomicReport,
    FsmEvent,
    FsmFullReport,
    Glitch,
    SingleMachineState,
)
from actors import command_reply
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.house0.channel_names import House0ChannelNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
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


def relay_full_report(relay: ShNode, cmd: FsmEvent) -> FsmFullReport:
    """The shape a relay actor reports a taken command in: one atomic under
    the command's TriggerId from the relay's own handle."""
    return FsmFullReport(
        FromName=relay.name,
        TriggerId=cmd.TriggerId,
        AtomicList=[
            FsmAtomicReport(
                MachineHandle=relay.handle,
                StateEnum=cmd.EventType,
                ReportType=FsmReportType.Event,
                EventEnum=cmd.EventType,
                Event=cmd.EventName,
                FromState="Unknown",
                ToState=cmd.EventName,
                UnixTimeMs=int(time.time() * 1000),
                TriggerId=cmd.TriggerId,
            )
        ],
    )


def capture(actor: SiegLoop, relays: str = "answer") -> list:
    """Replace the actor's sends with a list, and stand in for its two
    relays: `answer` acks every command and reports it in full, as a relay
    on a live board does; `ack_only` acks and never reports (the test
    delivers the reports, or lets the wait time out); `nack` refuses every
    command NotMyBoss."""
    sent: list = []
    loop_relays = {actor.layout.hp_loop_on_off.name, actor.layout.hp_loop_keep_send.name}

    def send_to(dst: ShNode, payload, src=None) -> None:
        sent.append((dst.name, payload))
        if not (isinstance(payload, FsmEvent) and dst.name in loop_relays):
            return
        if relays == "nack":
            deliver(actor, dst.name, command_reply.nack(
                dst.handle, payload.FromHandle, payload.TriggerId, ScadaCmdRefusalReason.NotMyBoss
            ))
            return
        deliver(actor, dst.name, command_reply.ack(dst.handle, payload.FromHandle, payload.TriggerId))
        if relays == "answer":
            deliver(actor, dst.name, relay_full_report(dst, payload))

    actor._send_to = send_to
    actor._send = lambda message: None  # the watchdog pat on the tick
    return sent


def glitches(sent: list) -> list[tuple[LogLevel, str]]:
    return [(p.Type, p.Summary) for _, p in sent if isinstance(p, Glitch)]


def full_reports(sent: list) -> list[FsmFullReport]:
    return [p for dst, p in sent if isinstance(p, FsmFullReport) and dst == CoreNodeNames.primary_scada]


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
@pytest.mark.asyncio
async def test_valve_movement_reaches_both_relays(
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
    standby: bool = False,
) -> tuple[ScadaApp, ManualClock]:
    """The fixture pair on a manual clock, with the ops word's strategy or
    Standby set."""
    layout, ops = PAIRS[pair]
    ops_dict = json.loads((CONFIG / ops).read_text())
    if strategy is not None:
        ops_dict["FamilyParams"]["SiegLoopStrategy"] = strategy.value
    if standby:
        ops_dict["Standby"] = True
        ops_dict["AcceptsDispatch"] = False
        ops_dict["DispatchRefusalReason"] = "Standby"
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
    for _ in range(20):
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
    app, _ = manual_app(tmp_path, strategy=SiegLoopStrategy.StratProtect, standby=True)
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
async def test_the_loop_subscribes_to_hp_boss_at_start_and_receives_its_states(app: ScadaApp) -> None:
    """The loop asks the scada for hp-boss's states when it starts, and the
    scada then sends it each state hp-boss reports."""
    actor = sieg_loop_actor(app)
    sent = capture(actor)
    actor.stop_requested = True  # the tick task ends at once
    actor.start()
    [subscribe] = [p for dst, p in sent if isinstance(p, MachineStateSubscribe)]
    assert subscribe.NodeName == actor.hp_boss.name

    scada = app.scada
    scada.process_scada_message(actor.node, subscribe)
    forwarded: list = []
    scada._send_to = lambda dst, payload, src=None: forwarded.append((dst.name, payload, src))
    state = hp_boss_state(actor, HpBossState.PreparingToTurnOn)
    scada.process_scada_message(actor.hp_boss, state)
    assert (actor.name, state, actor.hp_boss) in forwarded


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
    assert valve.keep_seconds == valve.FULL_RANGE_S - 40
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


# --- the relays answer -------------------------------------------------------


@pytest.mark.asyncio
async def test_an_automatic_move_reports_in_full_under_one_minted_id(tmp_path: Path) -> None:
    """The strategy's move to send: both relay commands carry one TriggerId
    the loop minted, the relays' acks and reports are neither logged nor
    glitched, and when the motor stops one full report goes to the scada
    under that id: the relays' atomics in order, then the loop's own with
    the valve's from and to states and no event."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = sieg_loop_actor(app)
    sent = capture(actor)
    deliver(actor, actor.primary_scada.name, ActuatorsReady())
    await settle()
    ids = {p.TriggerId for _, p in sent if isinstance(p, FsmEvent)}
    assert len(ids) == 1
    [move_id] = ids
    uuid.UUID(move_id)
    assert full_reports(sent) == []
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S)
    await settle()
    assert actor.valve.valve_state == SiegValveState.FullySend
    [report] = full_reports(sent)
    assert report.FromName == actor.name
    assert report.TriggerId == move_id
    assert [a.MachineHandle for a in report.AtomicList] == [
        actor.layout.hp_loop_keep_send.handle,
        actor.layout.hp_loop_on_off.handle,
        actor.layout.hp_loop_on_off.handle,
        actor.node.handle,
    ]
    own = report.AtomicList[-1]
    assert (own.StateEnum, own.EventEnum, own.Event, own.FromState, own.ToState) == (
        SiegValveState.enum_name(), None, None, SiegValveState.FullyKeep, SiegValveState.FullySend,
    )
    assert glitches(sent) == []


@pytest.mark.asyncio
async def test_the_motor_clock_starts_when_both_relays_have_reported(tmp_path: Path) -> None:
    """With the relays acking but not yet reporting, the valve machine says
    KeepingLess and the clock does not run: the full travel passes and the
    valve is still moving. Once both reports arrive the travel is timed
    from then."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = sieg_loop_actor(app)
    sent = capture(actor, relays="ack_only")
    deliver(actor, actor.primary_scada.name, ActuatorsReady())
    await settle()
    assert actor.valve.valve_state == SiegValveState.KeepingLess
    commands = [(dst, p) for dst, p in sent if isinstance(p, FsmEvent)]
    clock.advance(3)
    await settle()
    for dst, cmd in commands:
        deliver(actor, dst, relay_full_report(actor.layout.node(dst), cmd))
    await settle()
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S - 1)
    await settle()
    assert actor.valve.valve_state == SiegValveState.KeepingLess, "timed from the reports, not the command"
    clock.advance(1)
    await settle()
    assert actor.valve.valve_state == SiegValveState.FullySend
    assert glitches(sent) == []


@pytest.mark.asyncio
async def test_a_silent_relay_glitches_a_warning_and_the_clock_starts_anyway(tmp_path: Path) -> None:
    """No report within the wait: one warning glitch, then the travel is
    timed from the end of the wait. Enforcement below the loop keeps
    retrying a failed write, so the loop does not hold the valve hostage."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = sieg_loop_actor(app)
    sent = capture(actor, relays="ack_only")
    deliver(actor, actor.primary_scada.name, ActuatorsReady())
    await settle()
    clock.advance(actor.RELAY_REPORT_WAIT_S)
    await settle()
    assert glitches(sent) == [(LogLevel.Warning, "relay_silent")]
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S - 1)
    await settle()
    assert actor.valve.valve_state == SiegValveState.KeepingLess
    clock.advance(1)
    await settle()
    assert actor.valve.valve_state == SiegValveState.FullySend
    clock.advance(actor.RELAY_REPORT_WAIT_S)
    await settle()
    assert glitches(sent) == [(LogLevel.Warning, "relay_silent")] * 2, "the hold went unreported too"
    [report] = full_reports(sent)
    assert [a.MachineHandle for a in report.AtomicList] == [actor.node.handle], "nothing from the relays to fold"


@pytest.mark.asyncio
async def test_a_nack_ends_the_move_with_an_error_glitch(tmp_path: Path) -> None:
    """A relay refusing the command is a scada fault: one error glitch per
    nack, the motor is not started (the on/off relay is opened again),
    keep_seconds is untouched, and the move still reports in full."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = sieg_loop_actor(app)
    sent = capture(actor, relays="nack")
    deliver(actor, actor.primary_scada.name, ActuatorsReady())
    await settle()
    assert relay_events(sent) == TO_SEND + HOLD
    assert actor.valve.keep_seconds == actor.valve.FULL_RANGE_S
    assert glitches(sent) and all(g == (LogLevel.Error, "relay_nack") for g in glitches(sent))
    [report] = full_reports(sent)
    assert [a.MachineHandle for a in report.AtomicList] == [actor.node.handle]
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S)
    await settle()
    assert actor.valve.keep_seconds == actor.valve.FULL_RANGE_S, "the motor never ran"


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
    assert all(p.TriggerId == cmd.TriggerId for _, p in sent if isinstance(p, FsmEvent)), (
        "the relay commands ride under the commander's TriggerId"
    )
    [report] = full_reports(sent)
    assert report.TriggerId == cmd.TriggerId
    assert [a.MachineHandle for a in report.AtomicList] == [
        actor.layout.hp_loop_keep_send.handle,
        actor.layout.hp_loop_on_off.handle,
        actor.layout.hp_loop_on_off.handle,
        actor.node.handle,
    ], "both relays' atomics, then the loop's own"
    atomic = report.AtomicList[-1]
    assert (atomic.EventEnum, atomic.Event, atomic.FromState, atomic.ToState) == (
        MoveSiegValve.enum_name(), MoveSiegValve.MoveToFullKeep, SiegValveState.FullySend, SiegValveState.FullyKeep,
    )
    assert all(a.TriggerId == cmd.TriggerId for a in report.AtomicList)
    assert glitches(sent) == []

    sent.clear()
    for _ in range(3):
        actor.tick()
        clock.advance(actor.CONTROL_INTERVAL_S)
        await settle()
    assert relay_events(sent) == []
    assert actor.valve.valve_state == SiegValveState.FullyKeep


@pytest.mark.asyncio
async def test_stop_valve_mid_travel_holds_the_blend_and_reports_under_its_id(tmp_path: Path) -> None:
    """Admin's StopValve 40 s into a full run toward send from full keep:
    the motor stops, keep_seconds is what the clock says ran, the valve
    reads SteadyBlend, and one full report goes out under the StopValve's
    TriggerId with the hold's atomic and the loop's own. The cut-short move
    reports under its own id without the hold. The loop stays held."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = loop_under_admin(app)
    sent = capture(actor)
    valve = actor.valve
    assert valve.valve_state == SiegValveState.FullyKeep
    run = move(actor, MoveSiegValve.MoveToFullSend)
    deliver(actor, CoreNodeNames.admin, run)
    await settle()
    clock.advance(40)
    await settle()
    assert relay_events(sent) == TO_SEND

    stop = move(actor, MoveSiegValve.StopValve)
    deliver(actor, CoreNodeNames.admin, stop)
    await settle()
    assert replies(sent) == [(CoreNodeNames.admin, DispatchAck)] * 2
    assert relay_events(sent) == TO_SEND + HOLD
    hold = [p for dst, p in sent if isinstance(p, FsmEvent)][-1]
    assert hold.TriggerId == stop.TriggerId, "the hold rides under the stop's TriggerId"
    assert valve.keep_seconds == valve.FULL_RANGE_S - 40
    assert valve.valve_state == SiegValveState.SteadyBlend
    reports = {r.TriggerId: r for r in full_reports(sent)}
    assert set(reports) == {run.TriggerId, stop.TriggerId}
    assert [a.MachineHandle for a in reports[run.TriggerId].AtomicList] == [
        actor.layout.hp_loop_keep_send.handle,
        actor.layout.hp_loop_on_off.handle,
        actor.node.handle,
    ]
    stop_report = reports[stop.TriggerId]
    assert [a.MachineHandle for a in stop_report.AtomicList] == [
        actor.layout.hp_loop_on_off.handle,
        actor.node.handle,
    ]
    own = stop_report.AtomicList[-1]
    assert (own.EventEnum, own.Event, own.FromState, own.ToState) == (
        MoveSiegValve.enum_name(), MoveSiegValve.StopValve, SiegValveState.KeepingLess, SiegValveState.SteadyBlend,
    )
    assert all(a.TriggerId == stop.TriggerId for a in stop_report.AtomicList)
    assert glitches(sent) == []

    assert not actor.automatic
    sent.clear()
    for _ in range(3):
        actor.tick()
        clock.advance(actor.CONTROL_INTERVAL_S)
        await settle()
    assert relay_events(sent) == []
    assert valve.valve_state == SiegValveState.SteadyBlend
    assert valve.keep_seconds == valve.FULL_RANGE_S - 40


@pytest.mark.asyncio
async def test_stop_valve_with_the_motor_at_rest_moves_nothing(tmp_path: Path) -> None:
    """StopValve with no run in flight is acked, commands no relay, holds
    the loop, and reports the valve's state as it stands under its id."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = loop_under_admin(app)
    sent = capture(actor)
    stop = move(actor, MoveSiegValve.StopValve)
    deliver(actor, CoreNodeNames.admin, stop)
    await settle()
    assert replies(sent) == [(CoreNodeNames.admin, DispatchAck)]
    clock.advance(actor.valve.FULL_RANGE_S + actor.valve.OVERSHOOT_S)
    await settle()
    assert relay_events(sent) == []
    assert actor.valve.valve_state == SiegValveState.FullyKeep
    assert actor.valve.keep_seconds == actor.valve.FULL_RANGE_S
    assert not actor.automatic
    [report] = full_reports(sent)
    assert report.TriggerId == stop.TriggerId
    [own] = report.AtomicList
    assert (own.Event, own.FromState, own.ToState) == (
        MoveSiegValve.StopValve, SiegValveState.FullyKeep, SiegValveState.FullyKeep,
    )


@pytest.mark.asyncio
async def test_a_move_after_a_stop_runs_the_full_range_and_re_homes(tmp_path: Path) -> None:
    """From a stop at keep_seconds 60, MoveToFullSend still runs the whole
    range plus the overshoot and lands on FullySend at keep_seconds 0."""
    app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = loop_under_admin(app)
    sent = capture(actor)
    valve = actor.valve
    deliver(actor, CoreNodeNames.admin, move(actor, MoveSiegValve.MoveToFullSend))
    await settle()
    clock.advance(40)
    await settle()
    deliver(actor, CoreNodeNames.admin, move(actor, MoveSiegValve.StopValve))
    await settle()
    assert valve.keep_seconds == valve.FULL_RANGE_S - 40
    sent.clear()

    deliver(actor, CoreNodeNames.admin, move(actor, MoveSiegValve.MoveToFullSend))
    await settle()
    assert relay_events(sent) == TO_SEND
    clock.advance(valve.FULL_RANGE_S + valve.OVERSHOOT_S - 1)
    await settle()
    assert relay_events(sent) == TO_SEND, "a commanded move runs the full range from the stopped position"
    clock.advance(1)
    await settle()
    assert relay_events(sent) == TO_SEND + HOLD
    assert valve.valve_state == SiegValveState.FullySend
    assert valve.keep_seconds == 0


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


def test_capabilities_cover_sieg_loop_with_its_three_commands(app: ScadaApp) -> None:
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
        (MoveSiegValve.StopValve, SiegValveState.SteadyBlend),
    }
    assert House0NodeNames.hp_loop_on_off not in by_actor
    assert House0NodeNames.hp_loop_keep_send not in by_actor
    assert House0NodeNames.sieg_loop in {n.Name for n in caps.CommandNodes}


# --------------------------------------
# The sieg-view strip (debug output for the maple test-drives)
# --------------------------------------


def read(actor: SiegLoop, channel_name: str, value: int) -> None:
    actor.data.latest_channel_values[channel_name] = value
    actor.data.latest_channel_unix_ms[channel_name] = int(time.time() * 1000)


def view_names(line: str) -> set[str]:
    """The channel names on a sieg-view line, the derived mark stripped."""
    assert line.startswith("sieg-view ")
    body = line.split(" | ")[0].split(" ", 3)[3]
    return {part.split("=")[0].rstrip("*") for part in body.split()}


def test_the_view_names_every_neighbourhood_channel_the_layout_carries(app: ScadaApp) -> None:
    actor = sieg_loop_actor(app)
    line = actor.view()
    named = {name for name in VIEW_CHANNELS if actor.layout.channel_registry.get(name) is not None}
    assert view_names(line) == named
    assert HCN.hp_lwt in named and House0ChannelNames.sieg_flow in named
    derived = {n for n in named if isinstance(actor.layout.channel_registry.get(n), DerivedChannel)}
    assert derived, "each House0 fixture derives one of the three flows"
    for name in derived:
        assert f"{name}*=" in line


def test_the_view_carries_the_valve_position_after_its_state(app: ScadaApp) -> None:
    actor = sieg_loop_actor(app)
    assert actor.view().startswith(f"sieg-view {SiegValveState.FullyKeep} keep={float(actor.valve.FULL_RANGE_S)}s ")
    actor.valve.keep_seconds = 59.96
    assert " keep=60.0s " in actor.view()


def test_a_flushed_channel_shows_as_missing_until_it_reads_again(app: ScadaApp) -> None:
    actor = sieg_loop_actor(app)
    assert f"{HCN.hp_lwt}=--" in actor.view()
    read(actor, HCN.hp_lwt, 4512)  # CelsiusTimes100 in the fixtures
    assert f"{HCN.hp_lwt}=113.2F@0s" in actor.view()
    actor.data.flush_channel_from_latest(HCN.hp_lwt)
    assert f"{HCN.hp_lwt}=--" in actor.view()
    read(actor, HCN.hp_lwt, 4512)
    assert f"{HCN.hp_lwt}=113.2F@0s" in actor.view()


def test_the_blind_reason_on_the_line_matches_is_blind(app: ScadaApp) -> None:
    actor = sieg_loop_actor(app)
    strategy = actor.strategy
    assert isinstance(strategy, StratProtect)
    assert strategy.is_blind()
    assert "blind=no lift" in actor.view()
    read(actor, HCN.hp_lwt, 4500)
    read(actor, HCN.hp_ewt, 4000)
    assert "blind=no power" in actor.view()
    read(actor, HCN.hp_odu_pwr, 3000)
    read(actor, HCN.hp_idu_pwr, 200)
    assert not strategy.is_blind()
    line = actor.view()
    assert "blind=" not in line
    assert line.endswith("| lift=9.0F pwr=3200W")


@pytest.mark.asyncio
async def test_every_tick_and_valve_transition_writes_a_view_line(tmp_path: Path) -> None:
    scada_app, clock = manual_app(tmp_path, strategy=SiegLoopStrategy.HoldFullSend)
    actor = sieg_loop_actor(scada_app)
    capture(actor)
    lines: list[str] = []
    actor.log = lines.append
    actor.tick()
    assert sum(line.startswith("sieg-view ") for line in lines) == 1
    lines.clear()
    actor.valve.trigger_valve_event(SiegValveEvent.StartKeepingLess)
    assert [line for line in lines if line.startswith("sieg-view ")] == [actor.view()]
