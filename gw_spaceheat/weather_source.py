"""Where the scada's weather forecast comes from.

The derived generator and the LTN ask the scada's weather source for a
forecast and never reach a network themselves. A box pulls the bundle its
operational params name from the GridWorks weather service and keeps the
last forecast message and the bundle record beside it as sema instances,
read before any network call so a restart never waits on the service; a
test plant is given a simulated source whose forecast and response time
the test sets, so the suite never depends on a live service.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, tzinfo
from enum import auto
from pathlib import Path
from typing import Optional

import aiohttp
from gwsproto.enums import Unit
from gwsproto.enums.gw_str_enum import GwStrEnum
from gwsproto.named_types import (
    GwWeatherForecast,
    OperationalParams,
    WeatherForecast,
    WeatherForecastBundleGt,
)
from gwsproto.property_format import LeftRightDotStr
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Hours of forecast the consumers read.
FORECAST_HOURS = 48

# Whole units per scaled integer, by the channel's Unit.
UNIT_DIVISOR: dict[Unit, float] = {
    Unit.FahrenheitX100: 100.0,
    Unit.MilesPerHourX1000: 1000.0,
}

# Millinocket's coldest outdoor temperature by month (F), the last resort
# when no forecast is reachable or stored. Hand-kept until the weather
# service's SeasonalTemplate record exists; that word retires this list.
COLDEST_OAT_BY_MONTH = [-3, -7, 1, 21, 30, 31, 46, 47, 28, 24, 16, 0]


class WeatherSourceKind(GwStrEnum):
    Gwwf = auto()
    Sim = auto()


class WeatherSource(ABC):
    @abstractmethod
    async def forecast(
        self,
        session: aiohttp.ClientSession,
        *,
        tz: tzinfo,
        scada_g_node_alias: str,
    ) -> WeatherForecast:
        """The next 48 hourly slices of outdoor temperature and wind."""
        raise NotImplementedError


def coldest_of_the_month(scada_g_node_alias: str) -> WeatherForecast:
    """48 hourly slices from the next whole hour at the month's coldest temperature."""
    next_hour_s = (int(time.time()) // 3600 + 1) * 3600
    oat_f = float(COLDEST_OAT_BY_MONTH[datetime.now().month - 1])
    return WeatherForecast(
        FromGNodeAlias=scada_g_node_alias,
        WeatherChannelName="coldest.of.month",
        Time=[next_hour_s + h * 3600 for h in range(FORECAST_HOURS)],
        OatF=[oat_f] * FORECAST_HOURS,
        WindSpeedMph=[0.0] * FORECAST_HOURS,
    )


class GwwfWeatherSource(WeatherSource):
    """The latest forecast for one bundle from the GridWorks weather
    service's read facade, with the last message and the bundle record
    kept in the config dir and read first; the coldest temperature of the
    month behind both."""

    def __init__(
        self,
        bundle_name: LeftRightDotStr,
        api_url: str,
        config_dir: Path,
        timeout_s: float,
    ) -> None:
        self.bundle_name = bundle_name
        self.api_url = api_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)
        self.forecast_file = config_dir / f"{bundle_name}-gw.weather.forecast-000.json"
        self.bundle_file = config_dir / f"{bundle_name}-gw.weather.forecast.bundle.gt-000.json"
        self.bundle: Optional[WeatherForecastBundleGt] = self.stored_bundle()
        self.message: Optional[GwWeatherForecast] = self.stored_forecast()

    async def forecast(
        self,
        session: aiohttp.ClientSession,
        *,
        tz: tzinfo,
        scada_g_node_alias: str,
    ) -> WeatherForecast:
        pulled = await self.pull_forecast(session)
        if pulled is not None:
            self.message = pulled
        if self.message is not None and not self.bundle_matches(self.message):
            self.bundle = await self.pull_bundle(session)
        if self.message is None or self.bundle is None:
            logger.info("No forecast or bundle record; using the coldest of the month")
            return coldest_of_the_month(scada_g_node_alias)
        legacy = self.to_legacy(self.message, self.bundle, scada_g_node_alias)
        if legacy is None:
            logger.info(
                f"Forecast {self.message.FirstSliceStart} does not cover the next "
                f"{FORECAST_HOURS} hours; using the coldest of the month"
            )
            return coldest_of_the_month(scada_g_node_alias)
        return legacy

    def bundle_matches(self, message: GwWeatherForecast) -> bool:
        return (
            self.bundle is not None
            and self.bundle.Name == message.BundleName
            and self.bundle.TempForecastChannel.Name == message.TempChannelName
            and self.bundle.WindSpeedForecastChannel.Name == message.WindSpeedChannelName
        )

    async def pull_forecast(self, session: aiohttp.ClientSession) -> Optional[GwWeatherForecast]:
        url = f"{self.api_url}/latest-forecast/{self.bundle_name}"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    logger.info(f"Forecast pull {url} returned {response.status}")
                    return None
                message = GwWeatherForecast.model_validate(await response.json())
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            logger.info(f"Forecast pull {url} failed: {e!r}")
            return None
        self.forecast_file.write_text(message.model_dump_json(by_alias=True, indent=2))
        logger.info(
            f"Pulled a {len(message.TempValues)}-slice {message.Fidelity.value} forecast "
            f"starting {message.FirstSliceStart}"
        )
        return message

    async def pull_bundle(self, session: aiohttp.ClientSession) -> Optional[WeatherForecastBundleGt]:
        url = f"{self.api_url}/bundles"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    logger.info(f"Bundle pull {url} returned {response.status}")
                    return None
                records = [WeatherForecastBundleGt.model_validate(d) for d in await response.json()]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            logger.info(f"Bundle pull {url} failed: {e!r}")
            return None
        mine = [r for r in records if r.Name == self.bundle_name]
        if not mine:
            logger.info(f"The weather service has no bundle {self.bundle_name}")
            return None
        self.bundle_file.write_text(mine[0].model_dump_json(by_alias=True, indent=2))
        return mine[0]

    def stored_forecast(self) -> Optional[GwWeatherForecast]:
        if not self.forecast_file.exists():
            return None
        try:
            return GwWeatherForecast.model_validate_json(self.forecast_file.read_text())
        except ValidationError as e:
            logger.info(f"Stored forecast {self.forecast_file} does not decode: {e!r}")
            return None

    def stored_bundle(self) -> Optional[WeatherForecastBundleGt]:
        if not self.bundle_file.exists():
            return None
        try:
            return WeatherForecastBundleGt.model_validate_json(self.bundle_file.read_text())
        except ValidationError as e:
            logger.info(f"Stored bundle record {self.bundle_file} does not decode: {e!r}")
            return None

    @staticmethod
    def to_legacy(
        message: GwWeatherForecast,
        bundle: WeatherForecastBundleGt,
        scada_g_node_alias: str,
    ) -> Optional[WeatherForecast]:
        """The next 48 whole slices after now, unscaled per the bundle's units;
        None when fewer than 48 remain."""
        temp_unit = bundle.TempObservationChannel.Unit
        wind_unit = bundle.WindSpeedObservationChannel.Unit
        if temp_unit not in UNIT_DIVISOR or wind_unit not in UNIT_DIVISOR:
            raise ValueError(
                f"Bundle {bundle.Name} units {temp_unit.value}/{wind_unit.value} "
                "have no unscaling here"
            )
        start_s = int(datetime.fromisoformat(message.FirstSliceStart).timestamp())
        starts: list[int] = []
        for duration_s in bundle.TempForecastChannel.SliceDurationSList:
            starts.append(start_s)
            start_s += duration_s
        n = min(len(starts), len(message.TempValues))
        now_s = time.time()
        future = [i for i in range(n) if starts[i] > now_s][:FORECAST_HOURS]
        if len(future) < FORECAST_HOURS:
            return None
        return WeatherForecast(
            FromGNodeAlias=scada_g_node_alias,
            WeatherChannelName=message.TempChannelName,
            Time=[starts[i] for i in future],
            OatF=[message.TempValues[i] / UNIT_DIVISOR[temp_unit] for i in future],
            WindSpeedMph=[message.WindSpeedValues[i] / UNIT_DIVISOR[wind_unit] for i in future],
        )


class SimWeatherSource(WeatherSource):
    """A forecast the test sets, returned after a delay the test sets.
    With nothing set: 48 hourly slices from the top of the next hour,
    a steady 30 F and 5 mph."""

    WEATHER_CHANNEL = "sim.weather"

    def __init__(self) -> None:
        self.delay_s: float = 0
        self.forecast_to_return: Optional[WeatherForecast] = None

    async def forecast(
        self,
        session: aiohttp.ClientSession,
        *,
        tz: tzinfo,
        scada_g_node_alias: str,
    ) -> WeatherForecast:
        await asyncio.sleep(self.delay_s)
        if self.forecast_to_return is not None:
            return self.forecast_to_return
        next_hour_s = (int(time.time()) // 3600 + 1) * 3600
        return WeatherForecast(
            FromGNodeAlias=scada_g_node_alias,
            WeatherChannelName=self.WEATHER_CHANNEL,
            Time=[next_hour_s + h * 3600 for h in range(FORECAST_HOURS)],
            OatF=[30.0] * FORECAST_HOURS,
            WindSpeedMph=[5.0] * FORECAST_HOURS,
        )


def build_weather_source(
    kind: WeatherSourceKind,
    ops: OperationalParams,
    config_dir: Path,
    api_url: str,
    timeout_s: float,
) -> WeatherSource:
    """The weather source the settings ask for, on the bundle the ops word names."""
    if kind == WeatherSourceKind.Gwwf:
        return GwwfWeatherSource(ops.WeatherBundleName, api_url, config_dir, timeout_s)
    if kind == WeatherSourceKind.Sim:
        return SimWeatherSource()
    raise ValueError(f"Unknown weather source {kind}")
