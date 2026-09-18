"""derived-generator on the sim House0 fixture: one pass of its main loop
after the first heating forecast, the pass that computes usable energy from
the tank temperatures. Guards the partition residue where the actor lost its
temperature read a minute into every boot and its watchdog stopped the
scada."""

import datetime
import time
import uuid
from pathlib import Path

import pytest

from actors import derived_generator
from actors.derived_generator import DerivedGenerator
from gwsproto.named_types import HeatingForecast
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture(params=["orange", "willow"])
def app(request: pytest.FixtureRequest) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / f"gw.house0.{request.param}.layout.json"
    settings.paths.operational_params = CONFIG / f"gw.house0.{request.param}.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def a_day_of_forecast(actor: DerivedGenerator) -> HeatingForecast:
    """Hourly for 48 h from the next hour: a mild load, a required supply
    temperature below hot tanks, so extraction is possible."""
    top = int(time.time()) // 3600 * 3600 + 3600
    times = [top + 3600 * i for i in range(48)]
    return HeatingForecast(
        FromGNodeAlias=actor.layout.scada_g_node_alias,
        Time=times,
        AvgPowerKw=[3.0] * 48,
        RswtF=[120.0] * 48,
        RswtDeltaTF=[20.0] * 48,
        WeatherUid=str(uuid.uuid4()),
    )


def test_main_loop_pass_survives_the_first_forecast(app: ScadaApp) -> None:
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    data = actor.data
    data.heating_forecast = a_day_of_forecast(actor)
    data.buffer_temps_available = True
    for tank in actor.layout.store_tanks.values():
        for ch in (tank.depth1, tank.depth2, tank.depth3):
            data.latest_temperatures_f[ch] = 150.0
    for ch in (HCN.buffer.depth1, HCN.buffer.depth2, HCN.buffer.depth3):
        data.latest_temperatures_f[ch] = 150.0

    usable_wh = actor.compute_usable_energy_wh()
    assert isinstance(usable_wh, int) and usable_wh > 0

    sent: list = []
    actor._send = lambda message: sent.append(message)
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    for dc in actor.system_models:
        actor.handle_system_model(dc)
    assert sent, "the pass emits its derived readings"


MONDAY = datetime.datetime(2026, 1, 5)


def pin_clock(monkeypatch: pytest.MonkeyPatch, actor: DerivedGenerator, hour: int) -> None:
    """Pin the derived-generator module clock to Monday 2026-01-05 at `hour`,
    wall time in the actor's zone."""
    fixed = actor.timezone.localize(MONDAY + datetime.timedelta(hours=hour))

    class FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(derived_generator, "datetime", FixedDatetime)


def forecast_at(actor: DerivedGenerator, rswt_by_wall_time: dict[tuple[int, int], float]) -> HeatingForecast:
    """One forecast hour per `(days after Monday, hour)` key, carrying that
    required supply temperature."""
    times = [
        int(actor.timezone.localize(MONDAY + datetime.timedelta(days=d, hours=h)).timestamp())
        for d, h in rswt_by_wall_time
    ]
    return HeatingForecast(
        FromGNodeAlias=actor.layout.scada_g_node_alias,
        Time=times,
        AvgPowerKw=[3.0] * len(times),
        RswtF=list(rswt_by_wall_time.values()),
        RswtDeltaTF=[20.0] * len(times),
        WeatherUid=str(uuid.uuid4()),
        ForecastCreatedS=min(times) - 3600,
    )


@pytest.mark.parametrize(
    ("now_hour", "rswt_by_wall_time", "expected_rwt"),
    [
        # Evening, morning window ahead: both weekday windows count, so Tuesday
        # 08:00 (170 F) sets the bar and 150 F water gives up nothing.
        (21, {(0, 17): 140.0, (1, 8): 170.0}, 150.0),
        # A Saturday 08:00 hour is not on-peak in the ops word's windows, and
        # neither is a weekday 13:00: only Tuesday 17:00 (140 F) counts.
        (21, {(1, 17): 140.0, (5, 8): 170.0, (1, 13): 180.0}, 140.0),
        # Midday: only the afternoon window counts, Tuesday 08:00 does not.
        (13, {(0, 17): 140.0, (1, 8): 170.0}, 140.0),
    ],
)
def test_rwt_f_takes_its_onpeak_hours_from_the_ops_word(
    app: ScadaApp, monkeypatch: pytest.MonkeyPatch,
    now_hour: int, rswt_by_wall_time: dict[tuple[int, int], float], expected_rwt: float,
) -> None:
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    pin_clock(monkeypatch, actor, now_hour)
    actor.data.heating_forecast = forecast_at(actor, rswt_by_wall_time)
    monkeypatch.setattr(actor, "delta_T", lambda swt: 10.0)
    assert actor.rwt_f(150.0) == expected_rwt


def test_rwt_f_follows_a_changed_window(app: ScadaApp, monkeypatch: pytest.MonkeyPatch) -> None:
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    pin_clock(monkeypatch, actor, 21)
    actor.data.heating_forecast = forecast_at(actor, {(1, 8): 170.0, (1, 17): 140.0})
    monkeypatch.setattr(actor, "delta_T", lambda swt: 10.0)
    afternoon_only = [w for w in actor.ops.Tariff.OnPeakWindows if w.Start == "16:00"]
    tariff = actor.ops.Tariff.model_copy(update={"OnPeakWindows": afternoon_only})
    monkeypatch.setattr(actor.data, "ops", actor.ops.model_copy(update={"Tariff": tariff}))
    assert actor.rwt_f(150.0) == 140.0
