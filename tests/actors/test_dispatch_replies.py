"""Every command node answers its commander: DispatchAck once the command
is taken, DispatchNack with the reason when it is refused. One ack and one
refusal per actor, on both sim fixtures, with the tree held by admin so
the reply goes where the panel's button sends from."""

import asyncio
import time
import uuid
from pathlib import Path

import pytest

from actors.hp_boss import HpBoss
from actors.pico_cycler import PicoCycler
from actors.relay import Relay
from actors.zero_ten_outputer import ZeroTenOutputer
from gwproto.message import Header, Message
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import (
    ActorClass,
    ChangeRelayState,
    GwScadaCmdRefusalReason,
    MainAutoEvent,
    PicoCyclerState,
    RebootPicos,
    TurnHpOnOff,
)
from gwsproto.named_types import AnalogDispatch, DispatchAck, DispatchNack, FsmEvent
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
    scada_app.scada._send_to = lambda dst, payload, src=None: None
    scada_app.scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    return scada_app


def capture(actor) -> list:
    sent: list = []
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def event(to_handle: str, event_type: str, name: str) -> FsmEvent:
    return FsmEvent(
        FromHandle=H0N.admin,
        ToHandle=to_handle,
        EventType=event_type,
        EventName=name,
        SendTimeUnixMs=int(time.time() * 1000),
        TriggerId=str(uuid.uuid4()),
    )


def deliver(actor, payload) -> None:
    actor.process_message(
        Message(
            header=Header(Src=H0N.admin, Dst=actor.name, MessageType=payload.TypeName),
            Payload=payload,
        )
    )


def acks(sent: list) -> list[tuple[str, DispatchAck]]:
    return [(dst, p) for dst, p in sent if isinstance(p, DispatchAck)]


def nacks(sent: list) -> list[tuple[str, DispatchNack]]:
    return [(dst, p) for dst, p in sent if isinstance(p, DispatchNack)]


def assert_ack(sent: list, actor, command) -> None:
    assert nacks(sent) == []
    replies = acks(sent)
    assert len(replies) == 1
    dst, ack = replies[0]
    assert dst == H0N.admin
    assert ack.FromHandle == actor.node.handle
    assert ack.ToHandle == H0N.admin
    assert ack.TriggerId == command.TriggerId


def assert_nack(sent: list, actor, command, reason: GwScadaCmdRefusalReason) -> None:
    assert acks(sent) == []
    replies = nacks(sent)
    assert len(replies) == 1
    dst, nack = replies[0]
    assert dst == H0N.admin
    assert nack.FromHandle == actor.node.handle
    assert nack.ToHandle == H0N.admin
    assert nack.TriggerId == command.TriggerId
    assert nack.Reason == reason


# ---------------------------------------------------------------- pico-cycler

def cycler(app: ScadaApp) -> PicoCycler:
    actor = app.scada.get_communicator(H0N.pico_cycler)
    assert isinstance(actor, PicoCycler)
    assert actor.node.handle == f"{H0N.admin}.{H0N.pico_cycler}"
    return actor


def test_cycler_acks_a_reboot_it_takes(app: ScadaApp) -> None:
    actor = cycler(app)
    sent = capture(actor)
    command = event(actor.node.handle, RebootPicos.enum_name(), RebootPicos.RebootPicos)
    deliver(actor, command)
    assert actor.state == PicoCyclerState.RelayOpening
    assert_ack(sent, actor, command)


def test_cycler_refuses_busy_while_cycling(app: ScadaApp) -> None:
    actor = cycler(app)
    sent = capture(actor)
    deliver(actor, event(actor.node.handle, RebootPicos.enum_name(), RebootPicos.RebootPicos))
    sent.clear()
    second = event(actor.node.handle, RebootPicos.enum_name(), RebootPicos.RebootPicos)
    deliver(actor, second)
    assert_nack(sent, actor, second, GwScadaCmdRefusalReason.Busy)


def test_cycler_refuses_an_event_it_does_not_take(app: ScadaApp) -> None:
    actor = cycler(app)
    sent = capture(actor)
    command = event(actor.node.handle, ChangeRelayState.enum_name(), ChangeRelayState.OpenRelay)
    deliver(actor, command)
    assert actor.state == PicoCyclerState.PicosLive
    assert_nack(sent, actor, command, GwScadaCmdRefusalReason.UnknownEvent)


# ---------------------------------------------------------------- hp-boss

def hp_boss(app: ScadaApp) -> HpBoss:
    actor = app.get_communicator_as_type(H0N.hp_boss, HpBoss)
    assert actor is not None
    assert actor.node.handle == f"{H0N.admin}.{H0N.hp_boss}"
    return actor


def test_hp_boss_acks_turn_off(app: ScadaApp) -> None:
    actor = hp_boss(app)
    sent = capture(actor)
    command = event(actor.node.handle, TurnHpOnOff.enum_name(), TurnHpOnOff.TurnOff)
    deliver(actor, command)
    assert_ack(sent, actor, command)


def test_hp_boss_refuses_an_event_it_does_not_take(app: ScadaApp) -> None:
    actor = hp_boss(app)
    sent = capture(actor)
    command = event(actor.node.handle, RebootPicos.enum_name(), RebootPicos.RebootPicos)
    deliver(actor, command)
    assert_nack(sent, actor, command, GwScadaCmdRefusalReason.UnknownEvent)
    assert [p for _, p in sent if isinstance(p, FsmEvent)] == []


# ---------------------------------------------------------------- relay

def a_relay_under_admin(app: ScadaApp) -> Relay:
    """A relay the operator commands directly: its handle is admin.<name>."""
    layout = app.scada.layout
    for node in layout.nodes.values():
        if node.ActorClass == ActorClass.Relay and node.handle == f"{H0N.admin}.{node.name}":
            actor = app.scada.get_communicator(node.name)
            assert isinstance(actor, Relay)
            return actor
    raise AssertionError("no relay directly under admin on this layout")


@pytest.mark.asyncio
async def test_relay_acks_a_command_it_takes(app: ScadaApp) -> None:
    """The ack goes out before the actuation task the relay spawns."""
    actor = a_relay_under_admin(app)
    sent = capture(actor)
    vocabulary = actor.my_event_enum
    command = event(actor.node.handle, vocabulary.enum_name(), vocabulary.values()[0])
    actor._process_event_message(H0N.admin, command)
    assert_ack(sent, actor, command)
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()


def test_relay_refuses_an_event_it_does_not_take(app: ScadaApp) -> None:
    actor = a_relay_under_admin(app)
    sent = capture(actor)
    command = event(actor.node.handle, TurnHpOnOff.enum_name(), TurnHpOnOff.TurnOn)
    actor._process_event_message(H0N.admin, command)
    assert_nack(sent, actor, command, GwScadaCmdRefusalReason.UnknownEvent)


# ---------------------------------------------------------------- 0-10V outputer

def an_outputer(app: ScadaApp) -> ZeroTenOutputer:
    for name in app.get_communicator_names():
        actor = app.get_communicator(name)
        if isinstance(actor, ZeroTenOutputer):
            assert actor.node.handle == f"{H0N.admin}.{actor.name}"
            return actor
    raise AssertionError("no ZeroTenOutputer on this layout")


def dispatch(actor: ZeroTenOutputer, value: int) -> AnalogDispatch:
    return AnalogDispatch(
        FromGNodeAlias=None,
        FromHandle=H0N.admin,
        ToHandle=actor.node.handle,
        AboutName=actor.name,
        Value=value,
        TriggerId=str(uuid.uuid4()),
        UnixTimeMs=int(time.time() * 1000),
    )


def test_outputer_acks_a_value_in_range(app: ScadaApp) -> None:
    actor = an_outputer(app)
    sent = capture(actor)
    command = dispatch(actor, 55)
    deliver(actor, command)
    assert_ack(sent, actor, command)


def test_outputer_refuses_a_value_out_of_range(app: ScadaApp) -> None:
    actor = an_outputer(app)
    sent = capture(actor)
    command = dispatch(actor, 101)
    deliver(actor, command)
    assert_nack(sent, actor, command, GwScadaCmdRefusalReason.OutOfRange)
