"""The ally awaits its inputs. `initialize` is the ally's only Initializing
judgment: it awaits the first forecast and the first fresh buffer, then
judges once. Until then a contract puts the ally in Initializing with
SuitUp sent and the heat pump not on, and neither the main loop nor a second
contract judges. The scada's startup order holds the announcement back
until the first forecast, so an LTN that has no layout.lite cannot offer
early; the derived generator retries the first forecast with a Warning per
miss; the daily roster glitch says when a disabled channel is one dispatch
needs. The sim weather source's `release` pin holds the first fetch."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from gwproactor import MonitoredName

from actors.derived_generator import DerivedGenerator
from actors.leaf_ally.house0.all_tanks import AllTanksLeafAlly
from actors.leaf_ally.house0.buffer_only import BufferOnlyLeafAlly
from actors.hydronic.shared import dispatch_channels
from actors.scada import Scada
from gwsproto.enums import (
    LeafAllyAllTanksState,
    LeafAllyBufferOnlyState,
    LogLevel,
    MainAutoState,
    SeasonalStorageMode,
    SlowDispatchContractStatus,
    TurnHpOnOff,
)
from gwsproto.named_types import FsmEvent, Glitch, GoDormant, LayoutLite, MachineStates, SuitUp
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp
from sema_to_dc import load_layout
from tests.actors.test_cold_handling import CONFIG, WILLOW, heating_ops
from tests.actors.test_operating_status import ltn_hb
from tests.actors.test_startup_contract_load import (
    NOT_JUDGED,
    Sends,
    leaf_ally,
    live_contract,
    scada_tasks_started,
)
from tests.utils.scada_live_test_helper import ScadaLiveTest, fresh_buffer, ops_word_with
from weather_source import SimWeatherSource

MODES = {
    "buffer-only": SeasonalStorageMode.BufferOnly,
    "all-tanks": SeasonalStorageMode.AllTanks,
}
INITIALIZING = {LeafAllyAllTanksState.Initializing, LeafAllyBufferOnlyState.Initializing}
DORMANT = {LeafAllyAllTanksState.Dormant, LeafAllyBufferOnlyState.Dormant}
LOOP_S = 0.3  # the main-loop period, so a 60 s pass is a fraction of a second here
ALLY_FIRST_PASS_S = 2  # the ally's main loop sleeps this long before its first pass


def mode_ops(tmp_path: Path, mode: SeasonalStorageMode) -> Path:
    """Willow's ops word for a heating machine that accepts dispatch, with
    the ally the mode names."""
    return ops_word_with(
        heating_ops(tmp_path, WILLOW),
        tmp_path / f"{mode.value}-operational-params.json",
        seasonal_storage_mode=mode,
    )


class AllySends:
    """What the leaf ally sends, by destination, recorded and passed on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, scada: Scada) -> None:
        self.scada = scada
        self.impl = leaf_ally(scada)._impl
        self.sent: list[tuple[str, Any]] = []
        ally_send = self.impl._send_to

        def record(dst, payload, src=None):
            self.sent.append((dst.name, payload))
            ally_send(dst, payload, src)

        monkeypatch.setattr(self.impl, "_send_to", record)

    def of(self, payload_type: type) -> list[Any]:
        return [p for _, p in self.sent if isinstance(p, payload_type)]

    def hp_commands(self) -> list[str]:
        return [
            p.EventName for to, p in self.sent
            if isinstance(p, FsmEvent) and p.EventType == TurnHpOnOff.enum_name()
        ]

    def glitches(self) -> list[tuple[LogLevel, str]]:
        return [(p.Type, p.Summary) for p in self.of(Glitch)]


def quick_loop(monkeypatch: pytest.MonkeyPatch, *actor_types: type) -> None:
    """The actors' main loops at the test's period. The watchdog samples
    every few seconds, so the pat timeout stays on its own clock."""
    for actor_type in actor_types:
        monkeypatch.setattr(actor_type, "MAIN_LOOP_SLEEP_SECONDS", LOOP_S)
        monkeypatch.setattr(
            actor_type, "monitored_names", property(lambda self: [MonitoredName(self.name, 60)])
        )


def quick_allies(monkeypatch: pytest.MonkeyPatch) -> None:
    quick_loop(monkeypatch, AllTanksLeafAlly, BufferOnlyLeafAlly)


def held_weather(app: ScadaApp) -> SimWeatherSource:
    weather = app.weather_source
    assert isinstance(weather, SimWeatherSource)
    weather.release.clear()
    return weather


async def in_local_control(h: ScadaLiveTest, scada: Scada) -> None:
    await scada_tasks_started(h)
    await h.await_for(
        lambda: scada.auto_state == MainAutoState.LocalControl,
        "ERROR waiting for auto to wake into LocalControl",
        timeout=30,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", sorted(MODES), ids=sorted(MODES))
async def test_the_ally_judges_once_its_inputs_are_in(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """With the first fetch held open and a contract delivered, the ally is
    in Initializing with SuitUp sent and the heat pump not on, and makes no
    judgment through main-loop passes or a second contract delivered to
    it directly. Opening the pin runs the first judgment at once, with a
    forecast and no Warning glitch."""
    ops_path = mode_ops(tmp_path, MODES[mode])
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        app = h.child1_app
        weather = held_weather(app)
        quick_allies(monkeypatch)
        h.start_child1()
        scada = app.scada
        ally = leaf_ally(scada)
        await in_local_control(h, scada)
        sends = AllySends(monkeypatch, scada)
        fresh_buffer(scada)
        contract = live_contract(scada)
        scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
        await h.await_for(
            lambda: ally.state in INITIALIZING,
            "ERROR waiting for the ally to wake into Initializing",
            timeout=10,
            err_str_f=lambda: f"ally state: {ally.state}",
        )
        assert len(sends.of(SuitUp)) == 1
        assert TurnHpOnOff.TurnOn not in sends.hp_commands(), "the heat pump ran before a judgment"

        await asyncio.sleep(ALLY_FIRST_PASS_S + LOOP_S * 3)
        assert ally.state in INITIALIZING, "a main-loop pass judged without a forecast"
        ally._impl.process_slow_dispatch_contract(scada.node, live_contract(scada))
        await asyncio.sleep(LOOP_S * 2)
        assert ally.state in INITIALIZING, "a second contract judged without a forecast"
        assert not scada._data.first_forecast.is_set()
        assert sends.glitches() == []

        weather.release.set()
        await h.await_for(
            lambda: ally.state not in NOT_JUDGED,
            "ERROR waiting for the ally's first judgment",
            timeout=10,
            err_str_f=lambda: (
                f"ally state: {ally.state}, task: {ally._impl.initialize_task}, "
                f"first_forecast: {scada._data.first_forecast.is_set()}, "
                f"buffer_fresh_once: {scada._data.buffer_fresh_once.is_set()}, "
                f"glitches: {sends.glitches()}"
            ),
        )
        assert scada._data.heating_forecast is not None
        assert sends.glitches() == []


@pytest.mark.asyncio
async def test_go_dormant_while_awaiting_cancels_the_judgment(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops_path = mode_ops(tmp_path, SeasonalStorageMode.BufferOnly)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        app = h.child1_app
        weather = held_weather(app)
        quick_allies(monkeypatch)
        h.start_child1()
        scada = app.scada
        ally = leaf_ally(scada)
        await in_local_control(h, scada)
        fresh_buffer(scada)
        contract = live_contract(scada)
        scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
        await h.await_for(
            lambda: ally.state in INITIALIZING,
            "ERROR waiting for the ally to wake into Initializing",
            timeout=10,
        )
        task = ally._impl.initialize_task
        assert task is not None and not task.done()
        scada._send_to(scada.leaf_ally, GoDormant(ToName=scada.leaf_ally.name))
        await h.await_for(
            lambda: ally.state in DORMANT and task.done(),
            "ERROR waiting for the ally to go dormant and its judgment to be cancelled",
            timeout=10,
            err_str_f=lambda: f"ally state: {ally.state}, task done: {task.done()}",
        )
        assert task.cancelled()
        weather.release.set()
        await asyncio.sleep(LOOP_S * 3)
        assert ally.state in DORMANT


@pytest.mark.asyncio
async def test_the_announcement_waits_for_the_first_forecast(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the first fetch held open no layout.lite leaves the scada while
    state_tracker keeps reporting; opening the pin sends the announcement,
    and the offer that follows is accepted. An LTN primed to offer at once
    is stood in for by the offer delivered as soon as the layout.lite is
    out."""
    ops_path = heating_ops(tmp_path, WILLOW)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        app = h.child1_app
        weather = held_weather(app)
        app.settings.seconds_per_report = 5
        h.start_child1()
        scada = app.scada
        sends = Sends(monkeypatch, scada)
        await in_local_control(h, scada)
        await h.await_for(
            lambda: len([p for to, p in sends.sent if to == scada.node.name and isinstance(p, MachineStates)]) >= 2,
            "ERROR waiting for state_tracker's reports",
            timeout=30,
        )
        assert sends.to_ltn(LayoutLite) == [], "the layout.lite left before the first forecast"

        weather.release.set()
        await h.await_for(
            lambda: bool(sends.to_ltn(LayoutLite)),
            "ERROR waiting for the announcement",
            timeout=30,
        )
        fresh_buffer(scada)
        contract = live_contract(scada)
        scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
        assert scada.auto_state == MainAutoState.LeafTransactiveNode


@pytest.mark.asyncio
async def test_the_first_forecast_is_retried_with_a_warning_per_miss(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The weather source answers None twice, then a forecast: the first
    forecast is stored after the third fetch, with two Warning glitches."""
    ops_path = heating_ops(tmp_path, WILLOW)
    layout = load_layout(CONFIG / WILLOW[0], ops_path)
    quick_loop(monkeypatch, DerivedGenerator)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        app = h.child1_app
        weather = app.weather_source
        assert isinstance(weather, SimWeatherSource)
        weather.misses_left = 2
        weather.delay_s = 0.2  # the recorder below is installed inside the first fetch
        h.start_child1()
        generator = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
        assert generator is not None
        sent: list[Any] = []
        generator_send = generator._send_to

        def record(dst, payload, src=None):
            sent.append(payload)
            generator_send(dst, payload, src)

        monkeypatch.setattr(generator, "_send_to", record)
        await h.await_for(
            lambda: app.scada._data.first_forecast.is_set(),
            "ERROR waiting for the first forecast",
            timeout=30,
            err_str_f=lambda: f"fetches: {weather.fetches}",
        )
        assert weather.fetches == 3
        warnings = [(p.Type, p.Summary) for p in sent if isinstance(p, Glitch)]
        assert warnings == [(LogLevel.Warning, "no-weather-forecast")] * 2


def boot_with_disabled(tmp_path: Path, channels: list[str]) -> ScadaApp:
    layout = json.loads((CONFIG / WILLOW[0]).read_text())
    layout["DisabledChannelNames"] += channels
    layout_path = tmp_path / WILLOW[0]
    layout_path.write_text(json.dumps(layout))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout_path
    settings.paths.operational_params = CONFIG / WILLOW[1]
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def test_the_roster_glitch_names_a_disabled_dispatch_channel(tmp_path: Path) -> None:
    """When the disabled set meets the family's dispatch channels, the daily
    Warning says those channels are required for dispatch and the scada
    refuses every offer; a disabled channel dispatch does not need gets no
    such clause."""
    app = boot_with_disabled(tmp_path, [])
    needed = dispatch_channels(app.hardware_layout)[0]
    app = boot_with_disabled(tmp_path, [needed])
    glitch = app.scada.disabled_roster_glitch()
    assert glitch is not None
    assert glitch.Type == LogLevel.Warning
    assert "required for dispatch" in glitch.Details
    assert needed in glitch.Details
    assert "refuses every offer" in glitch.Details

    other = "dist-rwt"
    assert other not in dispatch_channels(app.hardware_layout)
    app = boot_with_disabled(tmp_path, [other])
    glitch = app.scada.disabled_roster_glitch()
    assert glitch is not None
    assert "required for dispatch" not in glitch.Details
