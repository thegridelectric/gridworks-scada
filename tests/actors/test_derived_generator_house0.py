"""derived-generator on the sim House0 fixture: one pass of its main loop
after the first forecasts, the pass that computes usable energy from the
tank temperatures and required energy from the forecasts. Guards the
partition residue where the actor lost its temperature read a minute into
every boot and its watchdog stopped the scada. The required-energy pass
runs at every hour of every weekday on a pinned clock, since which branch
it takes depends on the hour and the day."""

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
from weather_source import ForecastPair, sim_forecast

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


def forecast_hours(now_s: float) -> list[int]:
    """Hourly for 48 h from the hour after now_s."""
    top = int(now_s) // 3600 * 3600 + 3600
    return [top + 3600 * i for i in range(48)]


def a_weather_forecast(actor: DerivedGenerator, now_s: float | None = None) -> ForecastPair:
    """The weather forecast the generator holds whenever it holds a heating
    forecast: the simulated bundle from the next hour, a steady 30 F and no wind."""
    now_s = time.time() if now_s is None else now_s
    return sim_forecast(now_s, oat_f=30.0, wind_speed_mph=0.0)


def a_day_of_forecast(actor: DerivedGenerator, now_s: float | None = None) -> HeatingForecast:
    """Hourly for 48 h from the next hour: a mild load, a required supply
    temperature below hot tanks, so extraction is possible."""
    now_s = time.time() if now_s is None else now_s
    times = forecast_hours(now_s)
    return HeatingForecast(
        FromGNodeAlias=actor.layout.scada_g_node_alias,
        Time=times,
        AvgPowerKw=[3.0] * 48,
        RswtF=[120.0] * 48,
        RswtDeltaTF=[20.0] * 48,
        WeatherUid=str(uuid.uuid4()),
        ForecastCreatedS=int(now_s),
    )


def hot_tanks(actor: DerivedGenerator) -> None:
    data = actor.data
    data.buffer_temps_available = True
    for tank in actor.layout.store_tanks.values():
        for ch in (tank.depth1, tank.depth2, tank.depth3):
            data.latest_temperatures_f[ch] = 150.0
    for ch in (HCN.buffer.depth1, HCN.buffer.depth2, HCN.buffer.depth3):
        data.latest_temperatures_f[ch] = 150.0


def test_main_loop_pass_survives_the_first_forecast(app: ScadaApp) -> None:
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    data = actor.data
    data.heating_forecast = a_day_of_forecast(actor)
    actor.weather_forecast = a_weather_forecast(actor)
    hot_tanks(actor)

    usable_wh = actor.compute_usable_energy_wh()
    assert isinstance(usable_wh, int) and usable_wh > 0

    sent: list = []
    actor._send = lambda message: sent.append(message)
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    for dc in actor.system_models:
        actor.handle_system_model(dc)
    assert sent, "the pass emits its derived readings"


MONDAY = datetime.datetime(2026, 1, 5)


def pin_clock(
    monkeypatch: pytest.MonkeyPatch, actor: DerivedGenerator, hour: int, day: int = 0
) -> datetime.datetime:
    """Pin the derived-generator module clock to `hour` on the day `day`
    days after Monday 2026-01-05, wall time in the actor's zone. Returns
    the pinned time."""
    fixed = actor.timezone.localize(MONDAY + datetime.timedelta(days=day, hours=hour))

    class FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(derived_generator, "datetime", FixedDatetime)
    return fixed


@pytest.mark.parametrize("day", range(7), ids=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
def test_required_energy_at_every_hour_of_every_weekday(
    app: ScadaApp, monkeypatch: pytest.MonkeyPatch, day: int
) -> None:
    """With the two forecasts the field holds, the pass returns a
    non-negative number of watt-hours whatever the hour and the day."""
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    hot_tanks(actor)
    for hour in range(24):
        now = pin_clock(monkeypatch, actor, hour, day)
        actor.data.heating_forecast = a_day_of_forecast(actor, now.timestamp())
        actor.weather_forecast = a_weather_forecast(actor, now.timestamp())
        required_wh = actor.compute_required_energy_wh()
        assert isinstance(required_wh, int) and required_wh >= 0, f"day {day} hour {hour}"


@pytest.mark.parametrize("hour", [10, 13, 21])
def test_required_energy_without_a_weather_forecast_says_so(
    app: ScadaApp, monkeypatch: pytest.MonkeyPatch, hour: int
) -> None:
    """A heating forecast with no weather forecast behind it is a defect,
    and the pass names it at every hour rather than only in the hours
    that read the weather."""
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    hot_tanks(actor)
    now = pin_clock(monkeypatch, actor, hour)
    actor.data.heating_forecast = a_day_of_forecast(actor, now.timestamp())
    actor.weather_forecast = None
    with pytest.raises(RuntimeError, match="weather forecast"):
        actor.compute_required_energy_wh()


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


@pytest.mark.parametrize(
    ("now_day", "now_hour", "rswt_by_wall_time", "expected_rwt"),
    [
        # Friday evening: the 48 hours ahead are the weekend, with no on-peak
        # hour. The tariff's clock hours count on any day, so Saturday 08:00
        # (170 F) sets the bar; Saturday 13:00 is outside them.
        (4, 21, {(5, 8): 170.0, (5, 13): 180.0, (6, 17): 140.0}, 150.0),
        # Saturday midday: Monday 08:00 is on-peak but not an afternoon hour,
        # so no on-peak hour counts and Saturday 17:00 (140 F) sets the bar.
        (5, 13, {(5, 17): 140.0, (6, 8): 170.0, (7, 8): 175.0}, 140.0),
    ],
)
def test_rwt_f_with_no_onpeak_hour_ahead_takes_the_tariff_clock_hours_on_any_day(
    app: ScadaApp, monkeypatch: pytest.MonkeyPatch,
    now_day: int, now_hour: int,
    rswt_by_wall_time: dict[tuple[int, int], float], expected_rwt: float,
) -> None:
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    pin_clock(monkeypatch, actor, now_hour, now_day)
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
