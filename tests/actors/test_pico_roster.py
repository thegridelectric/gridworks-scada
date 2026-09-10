"""The pico-cycler reports each pico's health (single.pico.state) through
machine.states, keyed by the pico-backed actor's handle: the roster at
start, the flip when a pico flatlines (sent BEFORE the cycle it provokes),
the return to Alive, and the crossing into Zombie. The scada folds machine
states into report, so this is what the journal carries; which pico caused
a cycle is the one whose row flipped just before it.

Runs over both test layouts (every tank there is a sim pico)."""

import asyncio
from pathlib import Path

import pytest

from actors.config import ScadaSettings
from actors.pico_cycler import PicoCycler
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import PicoCyclerState, SinglePicoState
from gwsproto.named_types import Glitch, MachineStates, PicoMissing, SyncedReadings
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
LAYOUTS = ["nolan-layout.json", "house0-layout.json"]


@pytest.fixture(params=LAYOUTS)
def cycler(request: pytest.FixtureRequest) -> PicoCycler:
    settings = ScadaSettings(is_simulated=True)
    settings.paths.hardware_layout = CONFIG / request.param
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    c = app.scada.get_communicator(H0N.pico_cycler)
    assert isinstance(c, PicoCycler)
    assert c.picos, "fixture declares no picos"
    c.last_open_time = 0
    return c


def capture(cycler: PicoCycler) -> list:
    sent: list = []
    cycler._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def roster_rows(sent: list) -> list[MachineStates]:
    return [
        p for dst, p in sent
        if dst == H0N.primary_scada
        and isinstance(p, MachineStates)
        and p.StateEnum == SinglePicoState.enum_name()
    ]


def flatline(cycler: PicoCycler, actor) -> None:
    cycler.process_pico_missing(
        actor, PicoMissing(ActorName=actor.name, PicoHwUid=cycler.pico_by_actor[actor])
    )


def test_start_reports_every_pico_alive(cycler: PicoCycler) -> None:
    sent = capture(cycler)

    async def run() -> None:
        cycler.start()
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()

    asyncio.run(run())
    rows = roster_rows(sent)
    assert {r.MachineHandle for r in rows} == {a.handle for a in cycler.pico_actors}
    assert all(r.StateList == [SinglePicoState.Alive] for r in rows)


def test_flatlined_pico_row_precedes_the_cycle(cycler: PicoCycler) -> None:
    sent = capture(cycler)
    actor = cycler.pico_actors[0]
    flatline(cycler, actor)
    kinds = [
        (p.StateEnum, p.MachineHandle) for dst, p in sent if isinstance(p, MachineStates)
    ]
    assert kinds[0] == (SinglePicoState.enum_name(), actor.handle)
    assert (PicoCyclerState.enum_name(), cycler.node.handle) in kinds[1:]
    rows = roster_rows(sent)
    assert len(rows) == 1 and rows[0].StateList == [SinglePicoState.Flatlined]
    assert cycler.state == PicoCyclerState.RelayOpening


def test_second_missing_report_adds_no_row(cycler: PicoCycler) -> None:
    sent = capture(cycler)
    actor = cycler.pico_actors[0]
    flatline(cycler, actor)
    sent.clear()
    flatline(cycler, actor)
    assert roster_rows(sent) == []


def test_readings_bring_the_row_back_to_alive(cycler: PicoCycler) -> None:
    sent = capture(cycler)
    actor = cycler.pico_actors[0]
    flatline(cycler, actor)
    sent.clear()
    cycler.process_synced_readings(
        actor, SyncedReadings(ChannelNameList=[], ValueList=[], ScadaReadTimeUnixMs=1_700_000_000_000)
    )
    rows = roster_rows(sent)
    assert [r.StateList for r in rows] == [[SinglePicoState.Alive]]
    assert rows[0].MachineHandle == actor.handle
    # steady readings add nothing
    sent.clear()
    cycler.process_synced_readings(
        actor, SyncedReadings(ChannelNameList=[], ValueList=[], ScadaReadTimeUnixMs=1_700_000_000_000)
    )
    assert roster_rows(sent) == []


def test_zombie_threshold_reports_zombie(cycler: PicoCycler) -> None:
    actor = cycler.pico_actors[0]
    pico = cycler.pico_by_actor[actor]
    cycler.reboots[pico] = cycler.REBOOT_ATTEMPTS - 1
    sent = capture(cycler)
    flatline(cycler, actor)
    assert [r.StateList[0] for r in roster_rows(sent)] == [
        SinglePicoState.Flatlined,
        SinglePicoState.Zombie,
    ]
    assert any(isinstance(p, Glitch) and p.Summary == "pico-just-zombied" for _, p in sent)
    assert cycler.pico_state(pico) == SinglePicoState.Zombie
    # a zombie that posts again is Alive
    sent.clear()
    cycler.process_synced_readings(
        actor, SyncedReadings(ChannelNameList=[], ValueList=[], ScadaReadTimeUnixMs=1_700_000_000_000)
    )
    assert [r.StateList for r in roster_rows(sent)] == [[SinglePicoState.Alive]]


def test_rows_validate_on_the_wire(cycler: PicoCycler) -> None:
    sent = capture(cycler)
    cycler.report_pico_roster()
    for row in roster_rows(sent):
        MachineStates.model_validate(row.model_dump(by_alias=True, exclude_none=True))
