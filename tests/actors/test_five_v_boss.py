"""five-v-boss, the hold on the picos' 5 V: it sits under the tree's root in
every layout with the pico-cycler and vdc-relay under it. TurnOff sends the
cycler dormant, takes the relay and opens it; the open confirmation lands
FiveVOff. TurnOn closes the relay; the closed confirmation hands the relay
back and wakes the cycler. RebootPicos is forwarded to the cycler under the
command's TriggerId and the cycler's reply passed back. The scada's
AutoWakesUp restores the 5 V so LocalControl never inherits a dark fleet.

Runs over both sim fixtures with admin holding the tree."""

import time
import uuid
from pathlib import Path

import pytest
from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwproto.message import Header, Message

from actors.five_v_boss import FiveVBoss
from actors.pico_cycler import PicoCycler
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import (
    ChangeRelayState,
    FiveVBossState,
    FsmReportType,
    ScadaCmdRefusalReason,
    MainAutoEvent,
    PicoCyclerState,
    RebootPicos,
    RelayClosedOrOpen,
    Turn5VOnOff,
)
from gwsproto.named_types import (
    MachineStates,
    DispatchAck,
    DispatchNack,
    FsmAtomicReport,
    FsmEvent,
    FsmFullReport,
    GoDormant,
    NewCommandTree,
    PicoMissing,
    SingleMachineState,
    WakeUp,
)
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-sim": ("gw.house0.sim.layout.json", "gw.house0.sim.operational.params.json"),
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


def deliver(actor, payload, src: str) -> None:
    actor.process_message(
        Message(
            header=Header(Src=src, Dst=actor.name, MessageType=payload.TypeName),
            Payload=payload,
        )
    )


def relay_reported(app: ScadaApp, state: RelayClosedOrOpen) -> None:
    """The relay's last reported state on the scada's latest-state list."""
    app.scada._data.latest_machine_state[H0N.vdc_relay] = SingleMachineState(
        MachineHandle=app.scada.layout.vdc_relay.handle,
        StateEnum=RelayClosedOrOpen.enum_name(),
        State=state,
        UnixMs=int(time.time() * 1000),
    )


def boss_under_admin(app: ScadaApp) -> tuple[FiveVBoss, list]:
    scada = app.scada
    capture(scada)
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    boss = scada.get_communicator(H0N.five_v_boss)
    assert isinstance(boss, FiveVBoss)
    assert boss.node.handle == f"{H0N.admin}.{H0N.five_v_boss}"
    relay_reported(app, RelayClosedOrOpen.RelayClosed)
    return boss, capture(boss)


def command(to_handle: str, event_type: str, event_name: str, from_handle: str = H0N.admin) -> FsmEvent:
    return FsmEvent(
        FromHandle=from_handle,
        ToHandle=to_handle,
        EventType=event_type,
        EventName=event_name,
        SendTimeUnixMs=int(time.time() * 1000),
        TriggerId=str(uuid.uuid4()),
    )


def turn(boss: FiveVBoss, name: Turn5VOnOff) -> FsmEvent:
    return command(boss.node.handle, Turn5VOnOff.enum_name(), name)


def relay_confirmation(app: ScadaApp, event: ChangeRelayState, trigger_id: str) -> FsmFullReport:
    relay = app.scada.layout.vdc_relay
    to_state = RelayClosedOrOpen.RelayOpen if event == ChangeRelayState.OpenRelay else RelayClosedOrOpen.RelayClosed
    return FsmFullReport(
        FromName=relay.name,
        TriggerId=trigger_id,
        AtomicList=[
            FsmAtomicReport(
                MachineHandle=relay.handle,
                StateEnum=RelayClosedOrOpen.enum_name(),
                ReportType=FsmReportType.Event,
                EventEnum=ChangeRelayState.enum_name(),
                Event=event,
                FromState=RelayClosedOrOpen.RelayClosed if to_state == RelayClosedOrOpen.RelayOpen else RelayClosedOrOpen.RelayOpen,
                ToState=to_state,
                UnixTimeMs=int(time.time() * 1000),
                TriggerId=trigger_id,
            )
        ],
    )


def sent_of(sent: list, kind) -> list:
    return [(dst, p) for dst, p in sent if isinstance(p, kind)]


def hold_off(app: ScadaApp, boss: FiveVBoss, sent: list) -> FsmEvent:
    """TurnOff taken and the relay's open confirmed: FiveVOff."""
    cmd = turn(boss, Turn5VOnOff.TurnOff)
    deliver(boss, cmd, H0N.admin)
    assert boss.state == FiveVBossState.TurningOff
    deliver(boss, relay_confirmation(app, ChangeRelayState.OpenRelay, cmd.TriggerId), H0N.vdc_relay)
    assert boss.state == FiveVBossState.FiveVOff
    return cmd


# ---------------------------------------------------------------------------
# The tree
# ---------------------------------------------------------------------------


def test_tree_shape_under_every_boss(app: ScadaApp) -> None:
    """five-v-boss hangs under the root with the cycler and the relay under
    it, in the auto tree and the admin tree alike."""
    scada = app.scada
    capture(scada)
    layout = scada.layout
    assert layout.five_v_boss.handle == f"{H0N.auto}.{H0N.five_v_boss}"
    assert layout.pico_cycler.handle == f"{H0N.auto}.{H0N.five_v_boss}.{H0N.pico_cycler}"
    assert layout.vdc_relay.handle == f"{H0N.auto}.{H0N.five_v_boss}.{H0N.pico_cycler}.{H0N.vdc_relay}"
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    assert layout.five_v_boss.handle == f"{H0N.admin}.{H0N.five_v_boss}"
    assert layout.pico_cycler.handle == f"{H0N.admin}.{H0N.five_v_boss}.{H0N.pico_cycler}"
    assert layout.vdc_relay.handle == f"{H0N.admin}.{H0N.five_v_boss}.{H0N.pico_cycler}.{H0N.vdc_relay}"


def test_boot_state_and_report(app: ScadaApp) -> None:
    boss = app.scada.get_communicator(H0N.five_v_boss)
    assert isinstance(boss, FiveVBoss)
    assert boss.state == FiveVBossState.PicoCycler
    sent = capture(boss)
    boss.start()
    [(dst, sms)] = sent_of(sent, SingleMachineState)
    assert dst == H0N.primary_scada
    assert sms.State == FiveVBossState.PicoCycler
    assert sms.StateEnum == FiveVBossState.enum_name()


def test_capabilities_cover_five_v_boss_not_the_cycler(app: ScadaApp) -> None:
    """The panel commands five-v-boss with two vocabularies; the cycler and
    its relay are listed for their state and commanded through the boss."""
    caps = app.scada.control_capabilities
    by_actor: dict[str, list[str]] = {}
    for i in caps.CommandInterfaces:
        by_actor.setdefault(i.ActorName, []).append(i.EventType)
    assert sorted(by_actor[H0N.five_v_boss]) == sorted([Turn5VOnOff.enum_name(), RebootPicos.enum_name()])
    assert H0N.pico_cycler not in by_actor
    assert H0N.vdc_relay not in by_actor
    assert {n.Name for n in caps.CommandNodes} == {H0N.five_v_boss, H0N.pico_cycler, H0N.hp_boss}


def test_panel_row_gathers_both_vocabularies(app: ScadaApp) -> None:
    """The panel's five-v-boss row offers the three commands under their
    own event types (one row per node, two interfaces on this one); the
    cycler's row offers none."""
    configs = RelayWatchClient._get_relay_configs(app.scada.control_capabilities)
    boss = configs[H0N.five_v_boss]
    assert boss.state_type == FiveVBossState.enum_name()
    assert {(c.event_type, c.event, c.to_state) for c in boss.commands} == {
        (Turn5VOnOff.enum_name(), Turn5VOnOff.TurnOff, FiveVBossState.FiveVOff),
        (Turn5VOnOff.enum_name(), Turn5VOnOff.TurnOn, FiveVBossState.PicoCycler),
        (RebootPicos.enum_name(), RebootPicos.RebootPicos, FiveVBossState.PicoCycler),
    }
    assert configs[H0N.pico_cycler].commands == []


# ---------------------------------------------------------------------------
# The hold
# ---------------------------------------------------------------------------


def test_turn_off_takes_the_relay_and_opens_it(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    layout = app.scada.layout
    cmd = turn(boss, Turn5VOnOff.TurnOff)
    deliver(boss, cmd, H0N.admin)

    [(dst, ack)] = sent_of(sent, DispatchAck)
    assert dst == H0N.admin and ack.TriggerId == cmd.TriggerId
    [(dst, dormant)] = sent_of(sent, GoDormant)
    assert dst == H0N.pico_cycler and dormant.ToName == H0N.pico_cycler
    assert boss.state == FiveVBossState.TurningOff
    assert layout.vdc_relay.handle == f"{H0N.admin}.{H0N.five_v_boss}.{H0N.vdc_relay}"
    assert layout.pico_cycler.handle == f"{H0N.admin}.{H0N.five_v_boss}.{H0N.pico_cycler}"
    [(dst, tree)] = sent_of(sent, NewCommandTree)
    assert dst == H0N.ltn
    [(dst, event)] = sent_of(sent, FsmEvent)
    assert dst == H0N.vdc_relay
    assert event.EventName == ChangeRelayState.OpenRelay
    assert event.FromHandle == boss.node.handle
    assert event.ToHandle == layout.vdc_relay.handle
    assert event.TriggerId == cmd.TriggerId


def test_open_confirmation_lands_five_v_off_with_a_full_report(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    cmd = hold_off(app, boss, sent)
    [(dst, report)] = sent_of(sent, FsmFullReport)
    assert dst == H0N.primary_scada
    assert report.TriggerId == cmd.TriggerId
    assert [a.ToState for a in report.AtomicList] == [FiveVBossState.TurningOff, FiveVBossState.FiveVOff]
    assert [a.Event for a in report.AtomicList] == [Turn5VOnOff.TurnOff, Turn5VOnOff.TurnOff]
    assert report.AtomicList[0].FromState == FiveVBossState.PicoCycler
    states = [p.State for _, p in sent_of(sent, SingleMachineState)]
    assert states == [FiveVBossState.TurningOff, FiveVBossState.FiveVOff]


def test_turn_off_with_the_relay_open_is_busy(app: ScadaApp) -> None:
    """An open relay means the cycler is mid-cycle; the hold waits."""
    boss, sent = boss_under_admin(app)
    relay_reported(app, RelayClosedOrOpen.RelayOpen)
    cmd = turn(boss, Turn5VOnOff.TurnOff)
    deliver(boss, cmd, H0N.admin)
    [(dst, nack)] = sent_of(sent, DispatchNack)
    assert dst == H0N.admin
    assert nack.Reason == ScadaCmdRefusalReason.Busy
    assert nack.TriggerId == cmd.TriggerId
    assert boss.state == FiveVBossState.PicoCycler
    assert sent_of(sent, GoDormant) == []


def test_commands_while_turning_are_busy(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    deliver(boss, turn(boss, Turn5VOnOff.TurnOff), H0N.admin)
    assert boss.state == FiveVBossState.TurningOff
    for name in (Turn5VOnOff.TurnOn, Turn5VOnOff.TurnOff):
        deliver(boss, turn(boss, name), H0N.admin)
    reboot = command(boss.node.handle, RebootPicos.enum_name(), RebootPicos.RebootPicos)
    deliver(boss, reboot, H0N.admin)
    reasons = [p.Reason for _, p in sent_of(sent, DispatchNack)]
    assert reasons == [ScadaCmdRefusalReason.Busy] * 3
    assert boss.state == FiveVBossState.TurningOff


def test_turn_on_closes_and_the_closed_confirmation_hands_back(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    layout = app.scada.layout
    hold_off(app, boss, sent)
    del sent[:]

    cmd = turn(boss, Turn5VOnOff.TurnOn)
    deliver(boss, cmd, H0N.admin)
    [(dst, ack)] = sent_of(sent, DispatchAck)
    assert ack.TriggerId == cmd.TriggerId
    assert boss.state == FiveVBossState.TurningOn
    [(dst, event)] = sent_of(sent, FsmEvent)
    assert dst == H0N.vdc_relay
    assert event.EventName == ChangeRelayState.CloseRelay
    assert event.ToHandle == f"{H0N.admin}.{H0N.five_v_boss}.{H0N.vdc_relay}"
    assert sent_of(sent, WakeUp) == []

    deliver(boss, relay_confirmation(app, ChangeRelayState.CloseRelay, cmd.TriggerId), H0N.vdc_relay)
    assert boss.state == FiveVBossState.PicoCycler
    assert layout.vdc_relay.handle == f"{H0N.admin}.{H0N.five_v_boss}.{H0N.pico_cycler}.{H0N.vdc_relay}"
    [(dst, wake)] = sent_of(sent, WakeUp)
    assert dst == H0N.pico_cycler and wake.ToName == H0N.pico_cycler
    assert len(sent_of(sent, NewCommandTree)) == 1
    [(dst, report)] = sent_of(sent, FsmFullReport)
    assert report.TriggerId == cmd.TriggerId
    assert [a.ToState for a in report.AtomicList] == [FiveVBossState.TurningOn, FiveVBossState.PicoCycler]
    assert [a.Event for a in report.AtomicList] == [Turn5VOnOff.TurnOn, Turn5VOnOff.TurnOn]


def test_turn_on_at_rest_is_acked_and_does_nothing(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    cmd = turn(boss, Turn5VOnOff.TurnOn)
    deliver(boss, cmd, H0N.admin)
    [(dst, ack)] = sent_of(sent, DispatchAck)
    assert ack.TriggerId == cmd.TriggerId
    assert boss.state == FiveVBossState.PicoCycler
    assert sent_of(sent, FsmEvent) == []


def test_stale_relay_confirmation_is_ignored(app: ScadaApp) -> None:
    """A relay report under another id (a cycler cycle's) moves nothing."""
    boss, sent = boss_under_admin(app)
    deliver(boss, turn(boss, Turn5VOnOff.TurnOff), H0N.admin)
    deliver(boss, relay_confirmation(app, ChangeRelayState.OpenRelay, str(uuid.uuid4())), H0N.vdc_relay)
    assert boss.state == FiveVBossState.TurningOff
    assert sent_of(sent, FsmFullReport) == []


# ---------------------------------------------------------------------------
# The cycler under the boss
# ---------------------------------------------------------------------------


def test_reboot_picos_is_forwarded_and_the_reply_passed_back(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    cycler = app.scada.layout.pico_cycler
    cmd = command(boss.node.handle, RebootPicos.enum_name(), RebootPicos.RebootPicos)
    deliver(boss, cmd, H0N.admin)
    [(dst, forwarded)] = sent_of(sent, FsmEvent)
    assert dst == H0N.pico_cycler
    assert forwarded.FromHandle == boss.node.handle
    assert forwarded.ToHandle == cycler.handle
    assert forwarded.EventType == RebootPicos.enum_name()
    assert forwarded.TriggerId == cmd.TriggerId
    assert sent_of(sent, DispatchAck) == []

    deliver(
        boss,
        DispatchNack(
            FromHandle=cycler.handle, ToHandle=boss.node.handle, TriggerId=cmd.TriggerId,
            Reason=ScadaCmdRefusalReason.Busy, UnixTimeMs=int(time.time() * 1000),
        ),
        H0N.pico_cycler,
    )
    [(dst, nack)] = sent_of(sent, DispatchNack)
    assert dst == H0N.admin
    assert nack.TriggerId == cmd.TriggerId
    assert nack.Reason == ScadaCmdRefusalReason.Busy
    assert nack.FromHandle == boss.node.handle and nack.ToHandle == H0N.admin


def test_reboot_picos_reaches_the_real_cycler(app: ScadaApp) -> None:
    """End to end through the cycler actor: the forwarded command is taken
    as ShakeZombies under the command's id, and the ack comes back to admin."""
    boss, sent = boss_under_admin(app)
    cycler = app.scada.get_communicator(H0N.pico_cycler)
    assert isinstance(cycler, PicoCycler)
    cycler_sent = capture(cycler)
    cycler.state = PicoCyclerState.PicosLive
    cmd = command(boss.node.handle, RebootPicos.enum_name(), RebootPicos.RebootPicos)
    deliver(boss, cmd, H0N.admin)
    [(_, forwarded)] = sent_of(sent, FsmEvent)
    deliver(cycler, forwarded, H0N.five_v_boss)
    assert cycler.state == PicoCyclerState.RelayOpening
    assert cycler.trigger_id == cmd.TriggerId
    [(dst, ack)] = sent_of(cycler_sent, DispatchAck)
    assert dst == H0N.five_v_boss
    deliver(boss, ack, H0N.pico_cycler)
    [(dst, passed)] = sent_of(sent, DispatchAck)
    assert dst == H0N.admin and passed.TriggerId == cmd.TriggerId


def test_pico_missing_during_the_hold_cycles_nothing(app: ScadaApp) -> None:
    """The dormant cycler drops a PicoMissing: the picos are dark by design."""
    boss, sent = boss_under_admin(app)
    cycler = app.scada.get_communicator(H0N.pico_cycler)
    assert isinstance(cycler, PicoCycler)
    cycler_sent = capture(cycler)
    cycler.state = PicoCyclerState.PicosLive
    deliver(cycler, GoDormant(ToName=H0N.pico_cycler), H0N.five_v_boss)
    assert cycler.state == PicoCyclerState.Dormant
    # The Dormant row goes to the scada at the transition, not on the next
    # periodic report: the panel's cycler row flips with the boss's.
    [(dst, row)] = [(d, p) for d, p in cycler_sent if isinstance(p, MachineStates)]
    assert dst == H0N.primary_scada and row.StateList == [PicoCyclerState.Dormant]
    hold_off(app, boss, sent)
    cycler.last_open_time = 0
    actor = cycler.pico_actors[0]
    deliver(
        cycler,
        PicoMissing(ActorName=actor.name, PicoHwUid=cycler.pico_by_actor[actor]),
        actor.name,
    )
    assert cycler.state == PicoCyclerState.Dormant
    assert [p for _, p in cycler_sent if isinstance(p, FsmEvent)] == []


# ---------------------------------------------------------------------------
# Admin release
# ---------------------------------------------------------------------------


def test_wake_up_restores_the_five_v(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    hold_off(app, boss, sent)
    del sent[:]
    deliver(boss, WakeUp(ToName=H0N.five_v_boss), H0N.primary_scada)
    assert boss.state == FiveVBossState.TurningOn
    [(dst, event)] = sent_of(sent, FsmEvent)
    assert dst == H0N.vdc_relay and event.EventName == ChangeRelayState.CloseRelay
    assert boss.trigger_id == event.TriggerId
    deliver(boss, relay_confirmation(app, ChangeRelayState.CloseRelay, event.TriggerId), H0N.vdc_relay)
    assert boss.state == FiveVBossState.PicoCycler
    assert len(sent_of(sent, WakeUp)) == 1


def test_wake_up_at_rest_does_nothing(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    deliver(boss, WakeUp(ToName=H0N.five_v_boss), H0N.primary_scada)
    assert boss.state == FiveVBossState.PicoCycler
    assert sent == []


def test_scada_wakes_five_v_boss_on_admin_release(app: ScadaApp) -> None:
    """AutoWakesUp sends five-v-boss the wake.up LocalControl gets, and a
    tree rewritten while the hold is on keeps the relay under the boss."""
    scada = app.scada
    sent = capture(scada)
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    scada._data.latest_machine_state[H0N.five_v_boss] = SingleMachineState(
        MachineHandle=scada.layout.five_v_boss.handle,
        StateEnum=FiveVBossState.enum_name(),
        State=FiveVBossState.FiveVOff,
        UnixMs=int(time.time() * 1000),
    )
    del sent[:]
    scada.auto_trigger(MainAutoEvent.AutoWakesUp)
    assert scada.layout.vdc_relay.handle == f"{H0N.auto}.{H0N.five_v_boss}.{H0N.vdc_relay}"
    assert scada.layout.pico_cycler.handle == f"{H0N.auto}.{H0N.five_v_boss}.{H0N.pico_cycler}"
    wakes = {dst for dst, p in sent if isinstance(p, WakeUp)}
    assert wakes == {H0N.local_control, H0N.five_v_boss}


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_stale_handle_is_not_my_boss(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    cmd = command(f"{H0N.auto}.{H0N.five_v_boss}", Turn5VOnOff.enum_name(), Turn5VOnOff.TurnOff, from_handle=H0N.auto)
    deliver(boss, cmd, H0N.admin)
    [(dst, nack)] = sent_of(sent, DispatchNack)
    assert nack.Reason == ScadaCmdRefusalReason.NotMyBoss
    assert boss.state == FiveVBossState.PicoCycler


def test_unknown_event_is_refused(app: ScadaApp) -> None:
    boss, sent = boss_under_admin(app)
    cmd = command(boss.node.handle, ChangeRelayState.enum_name(), ChangeRelayState.OpenRelay)
    deliver(boss, cmd, H0N.admin)
    [(dst, nack)] = sent_of(sent, DispatchNack)
    assert nack.Reason == ScadaCmdRefusalReason.UnknownEvent
    assert sent_of(sent, FsmEvent) == []
