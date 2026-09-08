"""The pico-cycler's boss surface: one command, reboot the picos, ridden on
fsm.event with EventType reboot.picos addressed to the cycler's live handle
from its immediate boss. The cycler maps it onto ShakeZombies and adopts the
commander's TriggerId, so the relay's open and the cycle's own reports carry
the command's id. Anything else (a commander that is not the boss, a stale
handle, another event type) is refused the way relay.py refuses it. The
boot-time cycle enters through Startup, not PicoMissing.

Runs over both sim fixtures with admin holding the tree."""

import asyncio
import time
import uuid
from pathlib import Path

import pytest
from gwproto.message import Header, Message

from actors.pico_cycler import PicoCycler
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import (
    ChangeRelayState,
    GwScadaCmdRefusalReason,
    MainAutoEvent,
    PicoCyclerEvent,
    PicoCyclerState,
    RebootPicos,
    SinglePicoState,
)
from gwsproto.named_types import DispatchNack, FsmEvent, Glitch, MachineStates, PicoMissing
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


def cycler_under_admin(app: ScadaApp) -> tuple[PicoCycler, list]:
    scada = app.scada
    capture(scada)
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    cycler = scada.get_communicator(H0N.pico_cycler)
    assert isinstance(cycler, PicoCycler)
    assert cycler.node.handle == f"{H0N.admin}.{H0N.pico_cycler}"
    return cycler, capture(cycler)


def command(cycler: PicoCycler, event: FsmEvent, src: str = H0N.admin) -> None:
    cycler.process_message(
        Message(
            header=Header(Src=src, Dst=cycler.name, MessageType=event.TypeName),
            Payload=event,
        )
    )


def reboot_command(to_handle: str, from_handle: str = H0N.admin) -> FsmEvent:
    return FsmEvent(
        FromHandle=from_handle,
        ToHandle=to_handle,
        EventType=RebootPicos.enum_name(),
        EventName=RebootPicos.RebootPicos,
        SendTimeUnixMs=int(time.time() * 1000),
        TriggerId=str(uuid.uuid4()),
    )


def relay_events(sent: list) -> list[FsmEvent]:
    return [p for dst, p in sent if isinstance(p, FsmEvent)]


def test_boss_reboot_command_opens_relay_with_adopted_trigger_id(app: ScadaApp) -> None:
    cycler, sent = cycler_under_admin(app)
    event = reboot_command(cycler.node.handle)

    command(cycler, event)

    assert cycler.state == PicoCyclerState.RelayOpening
    opens = relay_events(sent)
    assert len(opens) == 1
    assert opens[0].ToHandle == app.scada.layout.vdc_relay.handle
    assert opens[0].FromHandle == cycler.node.handle
    assert opens[0].EventName == ChangeRelayState.OpenRelay
    assert opens[0].TriggerId == event.TriggerId
    assert cycler.trigger_id == event.TriggerId
    assert [r.Event for r in cycler.fsm_reports] == [PicoCyclerEvent.ShakeZombies]
    assert all(r.TriggerId == event.TriggerId for r in cycler.fsm_reports)
    cycler_rows = [
        p for dst, p in sent
        if isinstance(p, MachineStates) and p.StateEnum == PicoCyclerState.enum_name()
    ]
    assert [r.StateList for r in cycler_rows] == [[PicoCyclerState.RelayOpening]]


def test_command_to_stale_handle_is_refused_as_bad_boss(app: ScadaApp) -> None:
    """The auto node commanding the cycler by its auto-shape handle while
    admin holds the tree: the handle is not the cycler's live one."""
    cycler, sent = cycler_under_admin(app)

    command(
        cycler,
        reboot_command(f"{H0N.auto}.{H0N.pico_cycler}", from_handle=H0N.auto),
        src=H0N.auto,
    )

    assert cycler.state == PicoCyclerState.PicosLive
    assert relay_events(sent) == []
    glitches = [p for dst, p in sent if isinstance(p, Glitch)]
    assert [g.Summary for g in glitches] == ["bad_boss"]


def test_command_whose_from_handle_is_not_the_senders_is_refused(app: ScadaApp) -> None:
    cycler, sent = cycler_under_admin(app)
    forged = reboot_command(cycler.node.handle, from_handle=H0N.admin)
    forged = forged.model_copy(update={"FromHandle": H0N.auto})

    command(cycler, forged)

    assert cycler.state == PicoCyclerState.PicosLive
    assert sent == []


def test_other_event_types_are_refused(app: ScadaApp) -> None:
    """change.relay.state addressed to the cycler would be admin reaching
    through it to its relay; the cycler takes only reboot.picos."""
    cycler, sent = cycler_under_admin(app)
    event = FsmEvent(
        FromHandle=H0N.admin,
        ToHandle=cycler.node.handle,
        EventType=ChangeRelayState.enum_name(),
        EventName=ChangeRelayState.OpenRelay,
        SendTimeUnixMs=int(time.time() * 1000),
        TriggerId=str(uuid.uuid4()),
    )

    command(cycler, event)

    assert cycler.state == PicoCyclerState.PicosLive
    assert relay_events(sent) == []
    nacks = [p for _, p in sent if isinstance(p, DispatchNack)]
    assert [n.Reason for n in nacks] == [GwScadaCmdRefusalReason.UnknownEvent]
    assert nacks[0].TriggerId == event.TriggerId


def test_command_while_cycling_is_ignored(app: ScadaApp) -> None:
    cycler, sent = cycler_under_admin(app)
    first = reboot_command(cycler.node.handle)
    command(cycler, first)
    assert cycler.state == PicoCyclerState.RelayOpening

    command(cycler, reboot_command(cycler.node.handle))

    assert len(relay_events(sent)) == 1
    assert cycler.trigger_id == first.TriggerId


def test_boot_cycle_enters_through_startup(app: ScadaApp) -> None:
    cycler, sent = cycler_under_admin(app)

    cycler.startup()

    assert cycler.state == PicoCyclerState.RelayOpening
    assert [r.Event for r in cycler.fsm_reports] == [PicoCyclerEvent.Startup]
    assert [r.FromState for r in cycler.fsm_reports] == [PicoCyclerState.PicosLive]
    opens = relay_events(sent)
    assert len(opens) == 1
    assert opens[0].EventName == ChangeRelayState.OpenRelay
    assert opens[0].TriggerId == cycler.trigger_id


def test_reboot_wait_from_an_earlier_cycle_does_not_confirm_a_later_one(app: ScadaApp) -> None:
    """Cycle A's PICO_REBOOT_S wait fires while cycle B sits in
    PicosRebooting; B keeps waiting for its own picos. Seen on the
    dev-broker rung: a commanded cycle confirmed 3 s after its close by
    the self-provoked cycle's timer."""
    cycler, sent = cycler_under_admin(app)
    cycler.PICO_REBOOT_S = 0.05
    cycler.state = PicoCyclerState.PicosRebooting
    cycler.trigger_id = "cycle-a"

    async def cycle_b_takes_over() -> None:
        await asyncio.sleep(0.01)
        cycler.trigger_id = "cycle-b"
        cycler.fsm_reports = []

    async def run() -> None:
        await asyncio.gather(cycler._wait_for_rebooting_picos(), cycle_b_takes_over())

    asyncio.run(run())

    assert cycler.state == PicoCyclerState.PicosRebooting
    assert cycler.trigger_id == "cycle-b"
    assert cycler.fsm_reports == []
    assert not any(isinstance(p, FsmEvent) for dst, p in sent)


def test_relay_open_wait_from_an_earlier_cycle_does_not_close_for_a_later_one(app: ScadaApp) -> None:
    cycler, sent = cycler_under_admin(app)
    cycler.RELAY_OPEN_S = 0.05
    cycler.state = PicoCyclerState.RelayOpen
    cycler.trigger_id = "cycle-a"

    async def cycle_b_takes_over() -> None:
        await asyncio.sleep(0.01)
        cycler.trigger_id = "cycle-b"

    async def run() -> None:
        await asyncio.gather(cycler._wait_and_close_relay(), cycle_b_takes_over())

    asyncio.run(run())

    assert cycler.state == PicoCyclerState.RelayOpen
    assert not any(isinstance(p, FsmEvent) for dst, p in sent)


@pytest.mark.asyncio
async def test_pico_missing_during_a_commanded_cycle_is_expected(app: ScadaApp) -> None:
    """A pico cut by the relay open is silent by design: a PicoMissing
    inside the minute after the open leaves it Alive and reports no
    roster row; a minute on, the same report marks it Flatlined."""
    cycler, sent = cycler_under_admin(app)
    actor = cycler.pico_actors[0]
    pico = cycler.pico_by_actor[actor]
    cycler.last_open_time = time.time() - 3600
    command(cycler, reboot_command(cycler.node.handle))
    cycler.confirm_opened()
    assert cycler.state == PicoCyclerState.RelayOpen
    sent.clear()

    missing = PicoMissing(ActorName=actor.name, PicoHwUid=pico)
    cycler.process_pico_missing(actor, missing)
    assert cycler.pico_state(pico) == SinglePicoState.Alive
    assert [p for _, p in sent if isinstance(p, MachineStates)] == []

    cycler.last_open_time -= 61
    cycler.process_pico_missing(actor, missing)
    assert cycler.pico_state(pico) == SinglePicoState.Flatlined
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()
