"""The gwwf weather source against a local stand-in for the weather
service's read facade: the live Millinocket payloads, their FirstSliceStart
moved so the forecast covers the hours ahead of the test."""

import asyncio
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from aiohttp import web

from tests.named_types.weather_fixtures import BUNDLE_NAME, bundle_dict, forecast_dict
from weather_source import (
    COLDEST_OAT_BY_MONTH,
    FORECAST_HOURS,
    GwwfWeatherSource,
)

ET = ZoneInfo("America/New_York")
ALIAS = "hw1.isone.me.versant.keene.spruce.scada"


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
        self.forecast_hits = 0
        self.runner: Optional[web.AppRunner] = None
        self.url = ""

    async def bundles(self, request: web.Request) -> web.Response:
        self.bundle_hits += 1
        return web.json_response([bundle_dict()])

    async def latest_forecast(self, request: web.Request) -> web.Response:
        self.forecast_hits += 1
        await asyncio.sleep(self.delay_s)
        if self.forecast is None or request.match_info["name"] != BUNDLE_NAME:
            raise web.HTTPNotFound()
        return web.json_response(self.forecast)

    async def __aenter__(self) -> "Facade":
        app = web.Application()
        app.router.add_get("/hw1-isone-weather/bundles", self.bundles)
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


def source(config_dir: Path, url: str, timeout_s: float = 5) -> GwwfWeatherSource:
    return GwwfWeatherSource(BUNDLE_NAME, url, config_dir, timeout_s)


async def pull(src: GwwfWeatherSource):
    async with aiohttp.ClientSession() as session:
        return await src.forecast(session, tz=ET, scada_g_node_alias=ALIAS)


@pytest.mark.asyncio
async def test_a_pull_yields_48_future_hourly_slices_unscaled(tmp_path: Path) -> None:
    start_s = last_whole_hour_s()
    d = forecast_from(start_s)
    async with Facade(d) as facade:
        wf = await pull(source(tmp_path, facade.url))
    assert wf.Time == [start_s + 3600 * h for h in range(1, FORECAST_HOURS + 1)]
    assert wf.OatF == [v / 100 for v in d["TempValues"][1 : FORECAST_HOURS + 1]]
    assert wf.WindSpeedMph == [v / 1000 for v in d["WindSpeedValues"][1 : FORECAST_HOURS + 1]]
    assert wf.WeatherChannelName == d["TempChannelName"]
    assert wf.FromGNodeAlias == ALIAS
    stored = json.loads((tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast-000.json").read_text())
    assert stored == d
    bundle = json.loads((tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-000.json").read_text())
    assert bundle["Name"] == BUNDLE_NAME


@pytest.mark.asyncio
async def test_the_bundle_record_is_pulled_once_and_kept(tmp_path: Path) -> None:
    d = forecast_from(last_whole_hour_s())
    async with Facade(d) as facade:
        src = source(tmp_path, facade.url)
        await pull(src)
        await pull(src)
        assert facade.bundle_hits == 1
        assert facade.forecast_hits == 2
        # A new source on the same config dir reads the record from disk.
        await pull(source(tmp_path, facade.url))
        assert facade.bundle_hits == 1


@pytest.mark.asyncio
async def test_the_persisted_pair_serves_when_the_service_is_unreachable(tmp_path: Path) -> None:
    start_s = last_whole_hour_s()
    d = forecast_from(start_s)
    (tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast-000.json").write_text(json.dumps(d))
    (tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-000.json").write_text(json.dumps(bundle_dict()))
    wf = await pull(source(tmp_path, unreachable_url()))
    assert wf.Time[0] == start_s + 3600
    assert wf.OatF[0] == d["TempValues"][1] / 100


@pytest.mark.asyncio
async def test_a_persisted_forecast_outlives_a_pull_that_fails(tmp_path: Path) -> None:
    start_s = last_whole_hour_s()
    d = forecast_from(start_s)
    async with Facade(d) as facade:
        src = source(tmp_path, facade.url)
        await pull(src)
        facade.forecast = None  # the service now answers 404
        wf = await pull(src)
    assert wf.Time[0] == start_s + 3600
    assert wf.OatF[0] == d["TempValues"][1] / 100


@pytest.mark.asyncio
async def test_a_slow_service_is_bounded_by_the_timeout(tmp_path: Path) -> None:
    start_s = last_whole_hour_s()
    d = forecast_from(start_s)
    (tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast-000.json").write_text(json.dumps(d))
    (tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-000.json").write_text(json.dumps(bundle_dict()))
    async with Facade(d, delay_s=5) as facade:
        started = time.time()
        wf = await pull(source(tmp_path, facade.url, timeout_s=0.5))
        assert time.time() - started < 3
    assert wf.OatF[0] == d["TempValues"][1] / 100


@pytest.mark.asyncio
async def test_a_stale_persisted_forecast_falls_to_the_coldest_of_the_month(tmp_path: Path) -> None:
    d = forecast_from(last_whole_hour_s() - 5 * 24 * 3600)
    (tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast-000.json").write_text(json.dumps(d))
    (tmp_path / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-000.json").write_text(json.dumps(bundle_dict()))
    wf = await pull(source(tmp_path, unreachable_url()))
    assert wf.OatF == [float(COLDEST_OAT_BY_MONTH[datetime.now().month - 1])] * FORECAST_HOURS
    assert wf.WindSpeedMph == [0.0] * FORECAST_HOURS
    assert wf.Time[0] > time.time()


@pytest.mark.asyncio
async def test_nothing_persisted_and_no_service_is_the_coldest_of_the_month(tmp_path: Path) -> None:
    wf = await pull(source(tmp_path, unreachable_url()))
    assert wf.OatF == [float(COLDEST_OAT_BY_MONTH[datetime.now().month - 1])] * FORECAST_HOURS
    assert not list(tmp_path.glob("*gw.weather*"))
