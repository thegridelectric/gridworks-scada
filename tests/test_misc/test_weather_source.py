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

from gwsproto.named_types import GwWeatherForecast, WeatherForecastBundleGt
from tests.named_types.weather_fixtures import BUNDLE_NAME, LOCATION_ALIAS, bundle_dict, forecast_dict, template_dict
from clock import ManualClock, WallClock
from gwsproto.enums import WeatherForecastFidelity
from weather_source import (
    FORECAST_HOURS,
    ForecastPair,
    GwwfWeatherSource,
    SimWeatherSource,
    WeatherProvisioningError,
    sim_forecast,
    utc_seconds,
)



def last_whole_hour_s() -> int:
    return (int(time.time()) // 3600) * 3600


def forecast_from(start_s: int) -> dict:
    d = forecast_dict()
    d["FirstSliceStart"] = datetime.fromtimestamp(start_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d["MessageCreatedMs"] = int(time.time() * 1000)
    return d


class Facade:
    """A read facade on a free port, counting its hits."""

    def __init__(self, forecast: Optional[dict], delay_s: float = 0) -> None:
        self.forecast = forecast
        self.delay_s = delay_s
        self.bundle_hits = 0
        self.template_hits = 0
        self.templates: list[dict] = [template_dict()]
        self.forecast_hits = 0
        self.runner: Optional[web.AppRunner] = None
        self.url = ""

    async def bundles(self, request: web.Request) -> web.Response:
        self.bundle_hits += 1
        return web.json_response([bundle_dict()])

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
        (config_dir / f"{BUNDLE_NAME}-gw.weather.forecast-000.json").write_text(json.dumps(forecast))
    if bundle is not None:
        (config_dir / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-000.json").write_text(json.dumps(bundle))
    if template is not None:
        (config_dir / f"{LOCATION_ALIAS}-gw.weather.seasonal.template.gt-000.json").write_text(json.dumps(template))


def template_oat_f(at_s: float) -> float:
    """The template temperature of the UTC month at `at_s`."""
    month = datetime.fromtimestamp(at_s, tz=timezone.utc).month
    return template_dict()["TempByMonth"][month - 1] / 100


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
    assert hourly.oat_f == [v / 100 for v in d["TempValues"][1 : FORECAST_HOURS + 1]]
    assert hourly.wind_speed_mph == [v / 1000 for v in d["WindSpeedValues"][1 : FORECAST_HOURS + 1]]
    stored = json.loads((tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast-000.json").read_text())
    assert stored == d
    bundle = json.loads((tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-000.json").read_text())
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
    assert len(starts) == len(pair.message.TempValues)
    # Slices are counted from a chosen moment, not the wall clock.
    later = pair.next_hours(3, now_s=start_s + 10 * 3600)
    assert later.time == [start_s + 3600 * h for h in (11, 12, 13)]
    assert len(pair.next_hours(FORECAST_HOURS, now_s=start_s + 90 * 3600).time) == 5


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
        assert json.loads((tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-000.json").read_text()) == bundle_dict()
        assert json.loads((tmp_path / f"{LOCATION_ALIAS}-gw.weather.seasonal.template.gt-000.json").read_text()) == template_dict()
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
    assert pair.message.Fidelity == WeatherForecastFidelity.Live
    hourly = pair.next_hours(FORECAST_HOURS, time.time())
    assert hourly.time[0] == start_s + 3600
    assert hourly.oat_f[0] == d["TempValues"][1] / 100


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
    assert pair.next_hours(1, time.time()).oat_f[0] == d["TempValues"][1] / 100


@pytest.mark.asyncio
async def test_a_stale_persisted_forecast_is_filled_from_the_seasonal_template(tmp_path: Path) -> None:
    d = forecast_from(last_whole_hour_s() - 5 * 24 * 3600)
    persist(tmp_path, d, bundle_dict(), template_dict())
    pair = await pull(await source(tmp_path, unreachable_url()))
    assert pair is not None
    assert pair.message.Fidelity == WeatherForecastFidelity.SeasonalTemplate
    assert pair.message.BundleName == BUNDLE_NAME
    assert pair.bundle.model_dump(by_alias=True) == bundle_dict()
    assert len(pair.message.TempValues) == pair.bundle.TempForecastChannel.TotalSlices
    hourly = pair.next_hours(FORECAST_HOURS, time.time())
    assert hourly.oat_f == [template_oat_f(t) for t in hourly.time]
    assert hourly.wind_speed_mph == [0.0] * FORECAST_HOURS
    assert hourly.time[0] > time.time()


@pytest.mark.asyncio
async def test_a_bundle_record_and_template_alone_are_filled_from_the_template(tmp_path: Path) -> None:
    persist(tmp_path, None, bundle_dict(), template_dict())
    pair = await pull(await source(tmp_path, unreachable_url()))
    assert pair is not None
    assert pair.message.Fidelity == WeatherForecastFidelity.SeasonalTemplate
    hourly = pair.next_hours(FORECAST_HOURS, time.time())
    assert hourly.oat_f == [template_oat_f(t) for t in hourly.time]


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
    assert "96-slice Live forecast" in pulled[0].getMessage()


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
    assert utc_seconds(pair.message.SourceUpdatedTime) == int(plant_s)


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
    assert pair.message.Fidelity == WeatherForecastFidelity.Live
    assert pair.next_hours(1, inside.now()).time[0] == start_s + 11 * 3600
    beyond = ManualClock(start_s + 200 * 3600)
    pair = await pull(await source(tmp_path, unreachable_url(), clock=beyond))
    assert pair is not None
    assert pair.message.Fidelity == WeatherForecastFidelity.SeasonalTemplate
    assert pair.next_hours(1, beyond.now()).time[0] == (int(beyond.now()) // 3600 + 1) * 3600


def test_sim_forecast_takes_the_values_and_moment_a_test_sets() -> None:
    now_s = 1_800_000_000.0
    pair = sim_forecast(now_s, oat_f=-7.5, wind_speed_mph=0.0)
    hourly = pair.next_hours(FORECAST_HOURS, now_s)
    assert hourly.time[0] == (int(now_s) // 3600 + 1) * 3600
    assert hourly.oat_f == [-7.5] * FORECAST_HOURS
    assert pair.message.TempValues[0] == -750
