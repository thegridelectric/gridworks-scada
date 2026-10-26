"""The gwwf weather source against a local stand-in for the weather
service's read facade: the live Millinocket payloads, their FirstSliceStart
moved so the forecast covers the hours ahead of the test."""

import asyncio
import json
import logging
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp
import pytest
from aiohttp import web

from gwsproto.enums import Quantity, WeatherForecastFidelity
from gwsproto.named_types import GwWeatherForecast, WeatherForecastBundleGt, WeatherSeasonalTemplateGt
from tests.named_types.weather_fixtures import (
    BUNDLE_NAME,
    LOCATION_ALIAS,
    bundle_dict,
    forecast_dict,
    series_dict,
    template_dict,
)
from clock import ManualClock, WallClock
from weather_source import (
    FORECAST_HOURS,
    ForecastPair,
    GwwfWeatherSource,
    SimWeatherSource,
    WeatherProvisioningError,
    record_file,
    sim_forecast,
    utc_seconds,
)

# The fixture bundle's slice count; the pull tests need it to cover
# FORECAST_HOURS after the hour the message is issued in.
SLICES = len(series_dict("Temperature")["Values"])



def last_whole_hour_s() -> int:
    return (int(time.time()) // 3600) * 3600


def forecast_from(start_s: int, without: tuple[str, ...] = ()) -> dict:
    """The fixture message issued at `start_s`, less the series named in `without`."""
    d = forecast_dict()
    d["FirstSliceStart"] = datetime.fromtimestamp(start_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d["MessageCreatedMs"] = int(time.time() * 1000)
    d["SeriesList"] = [s for s in d["SeriesList"] if s["Quantity"] not in without]
    return d


def values_of(d: dict, quantity: str) -> list[int]:
    return next(s["Values"] for s in d["SeriesList"] if s["Quantity"] == quantity)


def bundle_without(quantity: str) -> dict:
    d = bundle_dict()
    d["BindingList"] = [b for b in d["BindingList"] if b["ObservationChannel"]["Quantity"] != quantity]
    return d


class Facade:
    """A read facade on a free port, counting its hits."""

    def __init__(self, forecast: Optional[dict], delay_s: float = 0, bundle: Optional[dict] = None) -> None:
        self.forecast = forecast
        self.delay_s = delay_s
        self.bundle = bundle_dict() if bundle is None else bundle
        self.bundle_hits = 0
        self.template_hits = 0
        self.templates: list[dict] = [template_dict()]
        self.forecast_hits = 0
        self.runner: Optional[web.AppRunner] = None
        self.url = ""

    async def bundles(self, request: web.Request) -> web.Response:
        self.bundle_hits += 1
        return web.json_response([self.bundle])

    async def seasonal_templates(self, request: web.Request) -> web.Response:
        self.template_hits += 1
        return web.json_response(self.templates)

    async def latest_forecast(self, request: web.Request) -> web.Response:
        self.forecast_hits += 1
        await asyncio.sleep(self.delay_s)
        if self.forecast is None or request.match_info["name"] != BUNDLE_NAME:
            raise web.HTTPNotFound()
        return web.json_response(self.forecast)

    async def __aenter__(self) -> "Facade":
        app = web.Application()
        app.router.add_get("/hw1-isone-weather/bundles", self.bundles)
        app.router.add_get("/hw1-isone-weather/seasonal-templates", self.seasonal_templates)
        app.router.add_get("/hw1-isone-weather/latest-forecast/{name}", self.latest_forecast)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        await web.TCPSite(self.runner, "127.0.0.1", port).start()
        self.url = f"http://127.0.0.1:{port}/hw1-isone-weather"
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self.runner is not None
        await self.runner.cleanup()


def unreachable_url() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}/hw1-isone-weather"


LOGGER_NAME = "gridworks.weather_source"


async def source(
    config_dir: Path, url: str, timeout_s: float = 5, clock: Optional[ManualClock] = None
) -> GwwfWeatherSource:
    """A source booted off the test's loop: boot pulls on the wall, and the
    facade answers on the loop."""
    return await asyncio.to_thread(
        GwwfWeatherSource,
        BUNDLE_NAME, url, config_dir, timeout_s, WallClock() if clock is None else clock, logging.getLogger(LOGGER_NAME),
    )


async def pull(src: GwwfWeatherSource) -> Optional[ForecastPair]:
    async with aiohttp.ClientSession() as session:
        return await src.forecast(session)


def persist(
    config_dir: Path, forecast: Optional[dict], bundle: Optional[dict], template: Optional[dict] = None
) -> None:
    if forecast is not None:
        record_file(config_dir, BUNDLE_NAME, GwWeatherForecast).write_text(json.dumps(forecast))
    if bundle is not None:
        record_file(config_dir, BUNDLE_NAME, WeatherForecastBundleGt).write_text(json.dumps(bundle))
    if template is not None:
        record_file(config_dir, LOCATION_ALIAS, WeatherSeasonalTemplateGt).write_text(json.dumps(template))


def template_oat_f(at_s: float) -> float:
    """The template temperature of the UTC month at `at_s`."""
    month = datetime.fromtimestamp(at_s, tz=timezone.utc).month
    template = WeatherSeasonalTemplateGt.model_validate(template_dict())
    return template.TempByMonth[month - 1] / 100


@pytest.mark.asyncio
async def test_a_pull_yields_the_served_pair_and_48_future_hourly_slices_unscaled(tmp_path: Path) -> None:
    start_s = last_whole_hour_s()
    d = forecast_from(start_s)
    async with Facade(d) as facade:
        pair = await pull(await source(tmp_path, facade.url))
    assert pair is not None
    assert pair.message.model_dump(by_alias=True) == d
    assert pair.bundle.model_dump(by_alias=True) == bundle_dict()
    hourly = pair.next_hours(FORECAST_HOURS, time.time())
    assert hourly.time == [start_s + 3600 * h for h in range(1, FORECAST_HOURS + 1)]
    assert hourly.oat_f == [v / 10 for v in values_of(d, "Temperature")[1 : FORECAST_HOURS + 1]]
    assert hourly.wind_speed_mph == [v / 10 for v in values_of(d, "WindSpeed")[1 : FORECAST_HOURS + 1]]
    stored = json.loads(record_file(tmp_path, BUNDLE_NAME, GwWeatherForecast).read_text())
    assert stored == d
    bundle = json.loads(record_file(tmp_path, BUNDLE_NAME, WeatherForecastBundleGt).read_text())
    assert bundle["Name"] == BUNDLE_NAME


def test_next_hours_walks_the_bundles_slice_grid_from_first_slice_start() -> None:
    start_s = last_whole_hour_s()
    pair = ForecastPair(
        GwWeatherForecast.model_validate(forecast_from(start_s)),
        WeatherForecastBundleGt.model_validate(bundle_dict()),
    )
    starts = pair.slice_starts()
    assert starts[0] == start_s
    assert [b - a for a, b in zip(starts, starts[1:])] == [3600] * (len(starts) - 1)
    assert len(starts) == SLICES
    # Slices are counted from a chosen moment, not the wall clock.
    later = pair.next_hours(3, now_s=start_s + 10 * 3600)
    assert later.time == [start_s + 3600 * h for h in (11, 12, 13)]
    assert len(pair.next_hours(FORECAST_HOURS, now_s=start_s + (SLICES - 6) * 3600).time) == 5


@pytest.mark.asyncio
async def test_the_bundle_record_and_template_are_provisioned_at_boot_and_kept(tmp_path: Path) -> None:
    """A bare config dir with the service reachable: boot pulls the bundle
    record and the location's template, writes both, and no pull asks for
    them again; a new source on the same config dir reads them from disk."""
    d = forecast_from(last_whole_hour_s())
    async with Facade(d) as facade:
        src = await source(tmp_path, facade.url)
        assert facade.bundle_hits == 1
        assert facade.template_hits == 1
        assert json.loads(record_file(tmp_path, BUNDLE_NAME, WeatherForecastBundleGt).read_text()) == bundle_dict()
        assert json.loads(record_file(tmp_path, LOCATION_ALIAS, WeatherSeasonalTemplateGt).read_text()) == template_dict()
        await pull(src)
        await pull(src)
        assert facade.bundle_hits == 1
        assert facade.template_hits == 1
        assert facade.forecast_hits == 2
        await pull(await source(tmp_path, facade.url))
        assert facade.bundle_hits == 1
        assert facade.template_hits == 1


@pytest.mark.asyncio
async def test_the_persisted_pair_serves_when_the_service_is_unreachable(tmp_path: Path) -> None:
    start_s = last_whole_hour_s()
    d = forecast_from(start_s)
    persist(tmp_path, d, bundle_dict(), template_dict())
    pair = await pull(await source(tmp_path, unreachable_url()))
    assert pair is not None
    assert pair.fidelity_label() == WeatherForecastFidelity.Live.value
    hourly = pair.next_hours(FORECAST_HOURS, time.time())
    assert hourly.time[0] == start_s + 3600
    assert hourly.oat_f[0] == values_of(d, "Temperature")[1] / 10


@pytest.mark.asyncio
async def test_a_persisted_forecast_outlives_a_pull_that_fails(tmp_path: Path) -> None:
    start_s = last_whole_hour_s()
    d = forecast_from(start_s)
    async with Facade(d) as facade:
        src = await source(tmp_path, facade.url)
        await pull(src)
        facade.forecast = None  # the service now answers 404
        pair = await pull(src)
    assert pair is not None
    assert pair.next_hours(1, time.time()).time[0] == start_s + 3600


@pytest.mark.asyncio
async def test_a_slow_service_is_bounded_by_the_timeout(tmp_path: Path) -> None:
    d = forecast_from(last_whole_hour_s())
    persist(tmp_path, d, bundle_dict())
    async with Facade(d, delay_s=5) as facade:
        started = time.time()
        pair = await pull(await source(tmp_path, facade.url, timeout_s=0.5))
        assert time.time() - started < 3
    assert pair is not None
    assert pair.next_hours(1, time.time()).oat_f[0] == values_of(d, "Temperature")[1] / 10


@pytest.mark.asyncio
async def test_a_stale_persisted_forecast_is_filled_from_the_seasonal_template(tmp_path: Path) -> None:
    d = forecast_from(last_whole_hour_s() - 5 * 24 * 3600)
    persist(tmp_path, d, bundle_dict(), template_dict())
    pair = await pull(await source(tmp_path, unreachable_url()))
    assert pair is not None
    assert pair.fidelity_label() == WeatherForecastFidelity.SeasonalTemplate.value
    assert pair.message.BundleName == BUNDLE_NAME
    assert pair.bundle.model_dump(by_alias=True) == bundle_dict()
    assert [s.Quantity for s in pair.message.SeriesList] == [Quantity.Temperature, Quantity.WindSpeed]
    assert len(pair.message.SeriesList[0].Values) == SLICES
    hourly = pair.next_hours(FORECAST_HOURS, time.time())
    assert hourly.oat_f == [template_oat_f(t) for t in hourly.time]
    assert hourly.wind_speed_mph == [0.0] * FORECAST_HOURS
    assert hourly.time[0] > time.time()


@pytest.mark.asyncio
async def test_a_bundle_record_and_template_alone_are_filled_from_the_template(tmp_path: Path) -> None:
    persist(tmp_path, None, bundle_dict(), template_dict())
    pair = await pull(await source(tmp_path, unreachable_url()))
    assert pair is not None
    assert pair.fidelity_label() == WeatherForecastFidelity.SeasonalTemplate.value
    hourly = pair.next_hours(FORECAST_HOURS, time.time())
    assert hourly.oat_f == [template_oat_f(t) for t in hourly.time]


@pytest.mark.asyncio
async def test_a_forecast_without_a_wind_series_is_filled_and_names_the_missing_series(tmp_path: Path) -> None:
    """The consumers read temperature and wind. A message with no wind
    series is filled from the template, wind calm, and the source names
    what was missing so the generator can raise its glitch; the next
    complete message clears it."""
    start_s = last_whole_hour_s()
    async with Facade(forecast_from(start_s, without=("WindSpeed",))) as facade:
        src = await source(tmp_path, facade.url)
        pair = await pull(src)
        assert pair is not None
        assert src.missing_quantities == [Quantity.WindSpeed]
        assert pair.fidelity_label() == WeatherForecastFidelity.SeasonalTemplate.value
        hourly = pair.next_hours(FORECAST_HOURS, time.time())
        assert hourly.oat_f == [template_oat_f(t) for t in hourly.time]
        assert hourly.wind_speed_mph == [0.0] * FORECAST_HOURS
        facade.forecast = forecast_from(start_s)
        pair = await pull(src)
        assert pair is not None
        assert src.missing_quantities == []
        assert pair.fidelity_label() == WeatherForecastFidelity.Live.value


@pytest.mark.asyncio
async def test_a_bundle_that_binds_no_wind_channel_fills_with_calm_wind(tmp_path: Path) -> None:
    """A bundle with temperature only serves its template fill with no
    wind series at all; the consumers read calm."""
    bundle = bundle_without("WindSpeed")
    async with Facade(forecast_from(last_whole_hour_s(), without=("WindSpeed", "Irradiance")), bundle=bundle) as facade:
        src = await source(tmp_path, facade.url)
        pair = await pull(src)
    assert pair is not None
    assert src.missing_quantities == [Quantity.WindSpeed]
    assert [s.Quantity for s in pair.message.SeriesList] == [Quantity.Temperature]
    hourly = pair.next_hours(FORECAST_HOURS, time.time())
    assert hourly.wind_speed_mph == [0.0] * FORECAST_HOURS
    assert hourly.oat_f == [template_oat_f(t) for t in hourly.time]


@pytest.mark.asyncio
async def test_a_bundle_that_binds_no_temperature_channel_does_not_boot(tmp_path: Path) -> None:
    persist(tmp_path, None, bundle_without("Temperature"), template_dict())
    with pytest.raises(WeatherProvisioningError, match="binds no Temperature channel"):
        await source(tmp_path, unreachable_url())


@pytest.mark.asyncio
async def test_a_bundle_record_without_a_template_does_not_boot(tmp_path: Path) -> None:
    """Provisioning without the service: the missing template stops the
    scada at boot, naming the config dir and the pull that failed."""
    persist(tmp_path, None, bundle_dict())
    url = unreachable_url()
    with pytest.raises(WeatherProvisioningError, match=f"seasonal template for {LOCATION_ALIAS}.*{url}"):
        await source(tmp_path, url)
    assert not list(tmp_path.glob("*seasonal.template*"))


@pytest.mark.asyncio
async def test_nothing_persisted_and_no_service_does_not_boot(tmp_path: Path) -> None:
    with pytest.raises(WeatherProvisioningError, match=f"bundle record {BUNDLE_NAME}"):
        await source(tmp_path, unreachable_url())
    assert not list(tmp_path.glob("*gw.weather*"))


@pytest.mark.asyncio
async def test_a_service_without_the_locations_template_does_not_boot(tmp_path: Path) -> None:
    persist(tmp_path, None, bundle_dict())
    async with Facade(forecast=None) as facade:
        facade.templates = []
        with pytest.raises(WeatherProvisioningError, match="the weather service has none"):
            await source(tmp_path, facade.url)


@pytest.mark.asyncio
async def test_a_pull_is_logged_under_the_scadas_base_logger(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    d = forecast_from(last_whole_hour_s())
    async with Facade(d) as facade:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            await pull(await source(tmp_path, facade.url))
    pulled = [r for r in caplog.records if r.name == LOGGER_NAME and r.getMessage().startswith("Pulled a ")]
    assert len(pulled) == 1
    assert pulled[0].levelno == logging.INFO
    assert f"{SLICES}-slice forecast" in pulled[0].getMessage()
    assert "Temperature Live" in pulled[0].getMessage()


@pytest.mark.asyncio
async def test_the_sim_source_returns_a_steady_pair_from_the_plants_next_hour() -> None:
    """Plant time, not the wall: a manual clock a year away sets the slices."""
    plant_s = 1_830_000_000.0
    clock = ManualClock(plant_s)
    src = SimWeatherSource(clock)
    async with aiohttp.ClientSession() as session:
        pair = await src.forecast(session)
    assert pair is not None
    assert pair.bundle is src.bundle
    assert pair.message.BundleName == src.bundle.Name
    assert pair.covers_next(FORECAST_HOURS, plant_s)
    hourly = pair.next_hours(FORECAST_HOURS, plant_s)
    assert hourly.oat_f == [30.0] * FORECAST_HOURS
    assert hourly.wind_speed_mph == [5.0] * FORECAST_HOURS
    assert hourly.time[0] == (int(plant_s) // 3600 + 1) * 3600
    assert all(utc_seconds(s.SourceUpdatedTime) == int(plant_s) for s in pair.message.SeriesList)


@pytest.mark.asyncio
async def test_the_gwwf_source_judges_coverage_and_fills_on_the_plant_clock(tmp_path: Path) -> None:
    """A persisted forecast five days old on the wall is current when the
    plant clock sits inside it; a plant clock past it is what makes it stale,
    and the fill starts from the plant's next hour."""
    start_s = last_whole_hour_s() - 5 * 24 * 3600
    persist(tmp_path, forecast_from(start_s), bundle_dict(), template_dict())
    inside = ManualClock(start_s + 10 * 3600)
    pair = await pull(await source(tmp_path, unreachable_url(), clock=inside))
    assert pair is not None
    assert pair.fidelity_label() == WeatherForecastFidelity.Live.value
    assert pair.next_hours(1, inside.now()).time[0] == start_s + 11 * 3600
    beyond = ManualClock(start_s + 200 * 3600)
    pair = await pull(await source(tmp_path, unreachable_url(), clock=beyond))
    assert pair is not None
    assert pair.fidelity_label() == WeatherForecastFidelity.SeasonalTemplate.value
    assert pair.next_hours(1, beyond.now()).time[0] == (int(beyond.now()) // 3600 + 1) * 3600


def test_sim_forecast_takes_the_values_and_moment_a_test_sets() -> None:
    now_s = 1_800_000_000.0
    pair = sim_forecast(now_s, oat_f=-7.5, wind_speed_mph=0.0)
    hourly = pair.next_hours(FORECAST_HOURS, now_s)
    assert hourly.time[0] == (int(now_s) // 3600 + 1) * 3600
    assert hourly.oat_f == [-7.5] * FORECAST_HOURS
    assert pair.message.SeriesList[0].Values[0] == -75


@pytest.mark.asyncio
async def test_the_sim_source_holds_a_fetch_while_release_is_clear() -> None:
    """A cleared `release` keeps the fetch open; setting it lets the pair
    through. The pin stands in for a service that has not answered yet."""
    src = SimWeatherSource(ManualClock(1_830_000_000.0))
    src.release.clear()
    async with aiohttp.ClientSession() as session:
        fetch = asyncio.create_task(src.forecast(session))
        await asyncio.sleep(0.2)
        assert not fetch.done()
        assert src.fetches == 0
        src.release.set()
        pair = await asyncio.wait_for(fetch, timeout=2)
    assert pair is not None
    assert src.fetches == 1


@pytest.mark.asyncio
async def test_the_sim_source_answers_none_for_each_miss_then_the_pair() -> None:
    src = SimWeatherSource(ManualClock(1_830_000_000.0))
    src.misses_left = 2
    async with aiohttp.ClientSession() as session:
        answers = [await src.forecast(session) for _ in range(4)]
    assert [a is None for a in answers] == [True, True, False, False]
    assert src.fetches == 4
    assert src.misses_left == 0
