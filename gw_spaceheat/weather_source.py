"""Where the scada's weather forecast comes from.

The derived generator asks its weather source for a forecast and never
reaches a network itself. A box pulls from the National Weather Service;
a test plant is given a simulated source whose forecast and response
time the test sets, so the suite never depends on a live weather API.
"""

import asyncio
import json
import logging
import math
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone, tzinfo
from enum import auto
from pathlib import Path
from typing import Optional

import aiohttp
from gwsproto.enums.gw_str_enum import GwStrEnum
from gwsproto.named_types import WeatherForecast

logger = logging.getLogger(__name__)


class WeatherSourceKind(GwStrEnum):
    Nws = auto()
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


class NwsWeatherSource(WeatherSource):
    """The gridpoint hourly product for a point, with the last pull kept
    in a file for the hours the API is unreachable and the coldest
    temperature of the month behind that."""

    # International Civil Aviation Organization: 4-char alphanumeric code
    # assigned to airports and weather observation stations
    ICAO_CODE = "KMLT"
    WEATHER_CHANNEL = f"weather.gov.{ICAO_CODE}".lower()
    COLDEST_OAT_BY_MONTH = [-3, -7, 1, 21, 30, 31, 46, 47, 28, 24, 16, 0]

    def __init__(self, latitude: float, longitude: float, weather_file: Path) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.weather_file = weather_file

    async def forecast(
        self,
        session: aiohttp.ClientSession,
        *,
        tz: tzinfo,
        scada_g_node_alias: str,
    ) -> WeatherForecast:
        try:
            url = f"https://api.weather.gov/points/{self.latitude},{self.longitude}"
            response = await session.get(url)
            if response.status != 200:
                logger.info(f"Error fetching weather forecast url: {response.status}")
                raise Exception()

            data = await response.json()
            forecast_hourly_url = data['properties']['forecastHourly']
            forecast_response = await session.get(forecast_hourly_url)
            if forecast_response.status != 200:
                logger.info(f"Error fetching hourly weather forecast: {forecast_response.status}")
                raise Exception()

            forecast_data = await forecast_response.json()
            forecasts_all = {
                datetime.fromisoformat(period['startTime']):
                period['temperature']
                for period in forecast_data['properties']['periods']
                if 'temperature' in period and 'startTime' in period
                and datetime.fromisoformat(period['startTime']) > datetime.now(tz=tz)
            }
            ws_forecasts_all = {
                datetime.fromisoformat(period['startTime']):
                int(period['windSpeed'].replace(' mph',''))
                for period in forecast_data['properties']['periods']
                if 'windSpeed' in period and 'startTime' in period
                and datetime.fromisoformat(period['startTime']) > datetime.now(tz=tz)
            }
            forecasts_48h = dict(list(forecasts_all.items())[:48])
            ws_forecasts_48h = dict(list(ws_forecasts_all.items())[:48])
            weather = {
                'time': [int(x.astimezone(timezone.utc).timestamp()) for x in list(forecasts_48h.keys())],
                'oat': list(forecasts_48h.values()),
                'ws': list(ws_forecasts_48h.values())
                }
            logger.info(f"Obtained a {len(forecasts_all)}-hour weather forecast starting at {weather['time'][0]}")

            # Save 96h weather forecast to a local file
            forecasts_96h = dict(list(forecasts_all.items())[:96])
            ws_forecasts_96h = dict(list(ws_forecasts_all.items())[:96])
            weather_96h = {
                'time': [int(x.astimezone(timezone.utc).timestamp()) for x in list(forecasts_96h.keys())],
                'oat': list(forecasts_96h.values()),
                'ws': list(ws_forecasts_96h.values()),
                }
            with open(self.weather_file, 'w') as f:
                json.dump(weather_96h, f, indent=4)

        except Exception as e:
            logger.info(f"[!] Unable to get weather forecast from API: {e}")
            try:
                # Try reading an old forecast from local file
                with open(self.weather_file, 'r') as f:
                    weather_96h = json.load(f)
                if weather_96h['time'][-1] >= time.time()+ 48*3600:
                    logger.info("A valid weather forecast is available locally.")
                    seconds_late = time.time() - weather_96h['time'][0]
                    hours_late = math.ceil(seconds_late/3600)
                    weather = {}
                    for key in weather_96h:
                        weather[key] = weather_96h[key][hours_late:hours_late+48]
                    if weather['oat'] == []:
                        raise Exception()
                    if weather['time'][0] < time.time():
                        raise Exception(f"Weather forecast start of {weather['time'][0]} is in the past!! Check math")
                else:
                    logger.info("No valid weather forecasts available locally. Using coldest of the current month.")
                    weather = self.coldest_of_the_month()
            except Exception as e:
                logger.info(f"Issue getting local weather forecast! Using coldest of the current month.\n Issue: {e}")
                weather = self.coldest_of_the_month()

        return WeatherForecast(
            FromGNodeAlias=scada_g_node_alias,
            WeatherChannelName=self.WEATHER_CHANNEL,
            Time = weather['time'],
            OatF = weather['oat'],
            WindSpeedMph= weather['ws'],
        )

    def coldest_of_the_month(self) -> dict:
        current_month = datetime.now().month-1
        return {
            'time': [int(time.time()+(1+x)*3600) for x in range(48)],
            'oat': [self.COLDEST_OAT_BY_MONTH[current_month]]*48,
            'ws': [0]*48,
        }


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
            Time=[next_hour_s + h * 3600 for h in range(48)],
            OatF=[30.0] * 48,
            WindSpeedMph=[5.0] * 48,
        )


def build_weather_source(
    kind: WeatherSourceKind, latitude: float, longitude: float, config_dir: Path
) -> WeatherSource:
    """The weather source the settings ask for."""
    if kind == WeatherSourceKind.Nws:
        return NwsWeatherSource(latitude, longitude, config_dir / "weather.json")
    if kind == WeatherSourceKind.Sim:
        return SimWeatherSource()
    raise ValueError(f"Unknown weather source {kind}")
