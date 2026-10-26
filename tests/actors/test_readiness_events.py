"""The two readiness facts on ScadaData, each a one-shot asyncio.Event: the
derived generator sets `first_forecast` when it stores its first heating
forecast, and the scada sets `buffer_fresh_once` on its reading path the
first time the family's dispatch channels are all fresh. `buffer_fresh` is
the one availability word; the family switch lives in `hydronic/shared.py`."""

import time

import pytest

from actors.derived_generator import DerivedGenerator
from actors.hydronic.shared import buffer_fresh, dispatch_channels
from gwsproto.named_types import SingleReading, SyncedReadings
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp
from tests.actors.test_derived_generator_house0 import a_day_of_forecast, a_weather_forecast
from tests.actors.test_sensor_freshness import NOLAN, WILLOW, make_app

PAIRS = {"nolan": NOLAN, "willow": WILLOW}


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    return make_app(PAIRS[request.param])


def synced(channels: tuple[str, ...], at_s: float) -> SyncedReadings:
    return SyncedReadings(
        ChannelNameList=list(channels),
        ValueList=[15_000] * len(channels),
        ScadaReadTimeUnixMs=int(at_s * 1000),
    )


def test_a_fresh_scada_data_has_both_events_unset(app: ScadaApp) -> None:
    data = app.scada.data
    assert not data.first_forecast.is_set()
    assert not data.buffer_fresh_once.is_set()
    assert not buffer_fresh(data, app.hardware_layout), "nothing has been read"


def test_dispatch_channels_are_the_familys(app: ScadaApp) -> None:
    """Each family names the channels its control needs to judge the buffer;
    every one is a channel of the layout."""
    channels = dispatch_channels(app.hardware_layout)
    assert channels, "a family with no dispatch channels can never dispatch"
    for name in channels:
        layout = app.hardware_layout
        assert name in layout.data_channels or name in layout.derived_channels, name


def test_buffer_fresh_once_is_set_on_the_synced_reading_path(app: ScadaApp) -> None:
    """Unset while one dispatch channel has never been read; set by the
    reading that completes the set; still set once a channel goes stale,
    since later blindness is the per-heartbeat gate's."""
    scada = app.scada
    channels = dispatch_channels(app.hardware_layout)
    now = time.time()
    scada.process_synced_readings(scada.node, synced(channels[:-1], now))
    assert not scada.data.buffer_fresh_once.is_set()
    assert not buffer_fresh(scada.data, app.hardware_layout)
    scada.process_synced_readings(scada.node, synced(channels[-1:], now))
    assert scada.data.buffer_fresh_once.is_set()
    assert buffer_fresh(scada.data, app.hardware_layout)
    scada.data.latest_channel_unix_ms[channels[0]] = int((now - 24 * 3600) * 1000)
    assert not buffer_fresh(scada.data, app.hardware_layout)
    assert scada.data.buffer_fresh_once.is_set()


def test_buffer_fresh_once_is_set_on_the_single_reading_path(app: ScadaApp) -> None:
    scada = app.scada
    channels = dispatch_channels(app.hardware_layout)
    now_ms = int(time.time() * 1000)
    for name in channels:
        assert not scada.data.buffer_fresh_once.is_set()
        scada.process_single_reading(
            scada.node, SingleReading(ChannelName=name, Value=15_000, ScadaReadTimeUnixMs=now_ms)
        )
    assert scada.data.buffer_fresh_once.is_set()


@pytest.mark.asyncio
async def test_first_forecast_is_set_when_the_first_heating_forecast_is_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset through a fetch the weather source answers with None; set by
    the fetch that stores a heating forecast; still set after the next."""
    app = make_app(WILLOW)
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    monkeypatch.setattr(actor, "_send_to", lambda dst, payload, src=None: None)
    weather: list = [None]

    async def get_weather(session) -> None:
        actor.weather_forecast = weather[0]

    monkeypatch.setattr(actor, "get_weather", get_weather)
    await actor.get_forecasts(None)
    assert actor.data.heating_forecast is None
    assert not actor.data.first_forecast.is_set()

    weather[0] = a_weather_forecast(actor)
    await actor.get_forecasts(None)
    assert actor.data.heating_forecast is not None
    assert actor.data.first_forecast.is_set()

    await actor.get_forecasts(None)
    assert actor.data.first_forecast.is_set()


def test_the_energy_passes_wait_for_a_fresh_buffer() -> None:
    """Both House0 passes answer None while the buffer is not fresh and a
    number once it is."""
    app = make_app(WILLOW)
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    actor.data.heating_forecast = a_day_of_forecast(actor)
    actor.weather_forecast = a_weather_forecast(actor)
    for tank in actor.layout.store_tanks.values():
        for ch in (tank.depth1, tank.depth2, tank.depth3):
            actor.data.latest_temperatures_f[ch] = 150.0
    for ch in dispatch_channels(app.hardware_layout):
        actor.data.latest_temperatures_f[ch] = 150.0
    assert actor.compute_usable_energy_wh() is None
    assert actor.compute_required_energy_wh() is None
    stamp = int(time.time() * 1000)
    for ch in dispatch_channels(app.hardware_layout):
        actor.data.latest_channel_unix_ms[ch] = stamp
    assert isinstance(actor.compute_usable_energy_wh(), int)
    assert isinstance(actor.compute_required_energy_wh(), int)


def test_a_nolan_generator_has_no_energy_model() -> None:
    """The layered energy models are House0's. A Nolan layout declares no
    system-model channel, so the generator registers none and the first
    forecast runs no energy update; a House0 layout declares both."""
    app = make_app(NOLAN)
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    assert actor.system_models == []
    mine = {
        dc.Name for dc in actor.layout.derived_channels.values()
        if dc.CreatedByNodeName == actor.name
    }
    assert not mine & {"usable-energy", "required-energy"}

    house0 = make_app(WILLOW).get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert house0 is not None
    assert {dc.Name for dc in house0.system_models} == {"usable-energy", "required-energy"}
