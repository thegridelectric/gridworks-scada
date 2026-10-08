"""Where the scada's weather forecast comes from.

The derived generator and the LTN ask the scada's weather source for a
forecast and never reach a network themselves. A box pulls the bundle its
operational params name from the GridWorks weather service and keeps the
last forecast message and the bundle record beside it as sema instances,
read before any network call so a restart never waits on the service; a
test plant is given a simulated source whose forecast and response time
the test sets, so the suite never depends on a live service. Behind the
forecast sits the location's seasonal template, laid on the bundle's grid
when no forecast covers the horizon. The bundle record and the template
are provisioning: the scada reads them from its config dir at boot, pulls
whichever is missing, and does not start without both, so a box installed
without the service is found out at its first boot rather than at its
first outage. Plant time comes from the scada's clock; only the pull
timeouts are on the wall.
"""

import asyncio
import json
import logging
import urllib.request
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import auto
from pathlib import Path
from typing import NamedTuple, Optional

import aiohttp
from gwsproto.enums import Quantity, Unit, WeatherForecastFidelity
from gwsproto.enums.gw_str_enum import GwStrEnum
from gwsproto.named_types import (
    GwWeatherForecast,
    OperationalParams,
    WeatherChannelGt,
    WeatherForecastBundleGt,
    WeatherForecastChannelGt,
    WeatherSeasonalTemplateGt,
)
from gwsproto.property_format import LeftRightDotStr, UTCSeconds
from pydantic import ValidationError

from clock import Clock

# Hours of forecast the consumers read.
FORECAST_HOURS = 48

# Whole units per scaled integer, by the channel's Unit.
UNIT_DIVISOR: dict[Unit, float] = {
    Unit.FahrenheitX100: 100.0,
    Unit.MilesPerHourX1000: 1000.0,
}


class WeatherSourceKind(GwStrEnum):
    Gwwf = auto()
    Sim = auto()


class HourlyForecast(NamedTuple):
    """Consecutive forecast slices after a moment, unscaled: the start of each
    slice in UTC seconds, its outdoor air temperature in °F and its wind
    speed in mph. A view derived from a ForecastPair, never stored or sent."""

    time: list[UTCSeconds]
    oat_f: list[float]
    wind_speed_mph: list[float]


class ForecastPair(NamedTuple):
    """A gw.weather.forecast message with the gw.weather.forecast.bundle.gt
    record it was emitted on. Slice times and units live on the record, so
    the message is read through the pair."""

    message: GwWeatherForecast
    bundle: WeatherForecastBundleGt

    def slice_starts(self) -> list[UTCSeconds]:
        """The start of every slice the message carries, from the message's
        FirstSliceStart along the bundle's slice grid."""
        start_s = utc_seconds(self.message.FirstSliceStart)
        starts: list[UTCSeconds] = []
        for duration_s in self.bundle.TempForecastChannel.SliceDurationSList[: len(self.message.TempValues)]:
            starts.append(start_s)
            start_s += duration_s
        return starts

    def next_hours(self, hours: int, now_s: float) -> HourlyForecast:
        """Up to `hours` slices starting after plant time `now_s`, unscaled
        per the bundle's observation units."""
        temp_divisor = unit_divisor(self.bundle, self.bundle.TempObservationChannel)
        wind_divisor = unit_divisor(self.bundle, self.bundle.WindSpeedObservationChannel)
        starts = self.slice_starts()
        future = [i for i in range(len(starts)) if starts[i] > now_s][:hours]
        return HourlyForecast(
            time=[starts[i] for i in future],
            oat_f=[self.message.TempValues[i] / temp_divisor for i in future],
            wind_speed_mph=[self.message.WindSpeedValues[i] / wind_divisor for i in future],
        )

    def covers_next(self, hours: int, now_s: float) -> bool:
        return len(self.next_hours(hours, now_s).time) >= hours


def utc_seconds(iso: str) -> UTCSeconds:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def utc_iso(seconds: float) -> str:
    return datetime.fromtimestamp(int(seconds), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unit_divisor(bundle: WeatherForecastBundleGt, channel: WeatherChannelGt) -> float:
    if channel.Unit not in UNIT_DIVISOR:
        raise ValueError(f"Bundle {bundle.Name} channel {channel.Name} unit {channel.Unit.value} has no unscaling here")
    return UNIT_DIVISOR[channel.Unit]


def next_whole_hour_s(now_s: float) -> int:
    return (int(now_s) // 3600 + 1) * 3600


def forecast_on(
    bundle: WeatherForecastBundleGt,
    fidelity: WeatherForecastFidelity,
    first_slice_start_s: int,
    oat_f: list[float],
    wind_speed_mph: list[float],
    now_s: float,
) -> GwWeatherForecast:
    """A gw.weather.forecast on `bundle` created at plant time `now_s`, the
    values scaled per its observation units, as many slices as the lists
    carry."""
    temp_divisor = unit_divisor(bundle, bundle.TempObservationChannel)
    wind_divisor = unit_divisor(bundle, bundle.WindSpeedObservationChannel)
    return GwWeatherForecast(
        BundleName=bundle.Name,
        SourceUpdatedTime=utc_iso(now_s),
        MessageCreatedMs=int(now_s * 1000),
        Fidelity=fidelity,
        FirstSliceStart=utc_iso(first_slice_start_s),
        TempChannelName=bundle.TempForecastChannel.Name,
        TempValues=[round(v * temp_divisor) for v in oat_f],
        WindSpeedChannelName=bundle.WindSpeedForecastChannel.Name,
        WindSpeedValues=[round(v * wind_divisor) for v in wind_speed_mph],
    )


def seasonal_fill(
    bundle: WeatherForecastBundleGt, template: WeatherSeasonalTemplateGt, now_s: float
) -> ForecastPair:
    """The bundle's whole slice grid from the next whole hour after plant
    time `now_s`, each slice at its month's template temperature and no
    wind, marked SeasonalTemplate."""
    start_s = next_whole_hour_s(now_s)
    oat_f: list[float] = []
    for duration_s in bundle.TempForecastChannel.SliceDurationSList:
        month = datetime.fromtimestamp(start_s, tz=timezone.utc).month
        oat_f.append(template.TempByMonth[month - 1] / 100)
        start_s += duration_s
    message = forecast_on(
        bundle,
        WeatherForecastFidelity.SeasonalTemplate,
        next_whole_hour_s(now_s),
        oat_f,
        [0.0] * len(oat_f),
        now_s,
    )
    return ForecastPair(message, bundle)


class WeatherSource(ABC):
    @abstractmethod
    async def forecast(self, session: aiohttp.ClientSession) -> Optional[ForecastPair]:
        """The latest forecast covering the next FORECAST_HOURS, or None when
        the source holds none."""
        raise NotImplementedError


class WeatherProvisioningError(RuntimeError):
    """The scada cannot start: a provisioning record (the bundle record or
    the seasonal template) is neither in the config dir nor obtainable
    from the weather service."""


class GwwfWeatherSource(WeatherSource):
    """The latest forecast for one bundle from the GridWorks weather
    service's read facade, with the last message, the bundle record and
    the location's seasonal template kept in the config dir and read
    first. The bundle record and the template are provisioning: boot
    pulls whichever is missing and raises WeatherProvisioningError when
    it cannot; the template fills behind the forecast."""

    def __init__(
        self,
        bundle_name: LeftRightDotStr,
        api_url: str,
        config_dir: Path,
        timeout_s: float,
        clock: Clock,
        logger: logging.Logger,
    ) -> None:
        self.bundle_name = bundle_name
        self.api_url = api_url.rstrip("/")
        self.timeout_s = timeout_s
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)
        self.clock = clock
        self.logger = logger
        self.config_dir = config_dir
        self.forecast_file = config_dir / f"{bundle_name}-gw.weather.forecast-000.json"
        self.bundle_file = config_dir / f"{bundle_name}-gw.weather.forecast.bundle.gt-000.json"
        self.bundle: Optional[WeatherForecastBundleGt] = self.stored_bundle()
        if self.bundle is None:
            self.bundle = self.provision_bundle()
        self.template: Optional[WeatherSeasonalTemplateGt] = self.stored_template(self.bundle.LocationAlias)
        if self.template is None:
            self.template = self.provision_template(self.bundle.LocationAlias)
        self.message: Optional[GwWeatherForecast] = self.stored_forecast()

    def template_file(self, location_alias: LeftRightDotStr) -> Path:
        return self.config_dir / f"{location_alias}-gw.weather.seasonal.template.gt-000.json"

    def provision_records(self, path: str, what: str) -> list[dict]:
        """A read-facade listing pulled at boot, before the scada's loop
        runs; failure to reach it is failure to start."""
        url = f"{self.api_url}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_s) as response:
                return json.load(response)
        except (OSError, ValueError) as e:
            raise WeatherProvisioningError(
                f"No {what} in {self.config_dir} and the weather service pull {url} failed: {e!r}"
            ) from e

    def provision_bundle(self) -> WeatherForecastBundleGt:
        what = f"bundle record {self.bundle_name}"
        records = [WeatherForecastBundleGt.model_validate(d) for d in self.provision_records("bundles", what)]
        mine = [r for r in records if r.Name == self.bundle_name]
        if not mine:
            raise WeatherProvisioningError(f"No {what} in {self.config_dir} and the weather service has none")
        self.bundle_file.write_text(mine[0].model_dump_json(by_alias=True, indent=2))
        self.logger.info(f"Provisioned the {what} from the weather service")
        return mine[0]

    def provision_template(self, location_alias: LeftRightDotStr) -> WeatherSeasonalTemplateGt:
        what = f"seasonal template for {location_alias}"
        records = [
            WeatherSeasonalTemplateGt.model_validate(d) for d in self.provision_records("seasonal-templates", what)
        ]
        now_s = self.clock.now()
        mine = [r for r in records if r.LocationAlias == location_alias and utc_seconds(r.Start) <= now_s]
        if not mine:
            raise WeatherProvisioningError(f"No {what} in {self.config_dir} and the weather service has none")
        template = max(mine, key=lambda r: r.Start)
        self.template_file(location_alias).write_text(template.model_dump_json(by_alias=True, indent=2))
        self.logger.info(f"Provisioned the {what} from the weather service")
        return template

    async def forecast(self, session: aiohttp.ClientSession) -> Optional[ForecastPair]:
        pulled = await self.pull_forecast(session)
        if pulled is not None:
            self.message = pulled
        if self.bundle is None or (self.message is not None and not self.bundle_matches(self.message)):
            self.bundle = await self.pull_bundle(session)
        if self.bundle is None:
            self.logger.warning(f"No bundle record for {self.bundle_name} stored or reachable; no forecast")
            return None
        now_s = self.clock.now()
        if self.message is None:
            why = "No forecast stored or reachable"
        else:
            pair = ForecastPair(self.message, self.bundle)
            if pair.covers_next(FORECAST_HOURS, now_s):
                return pair
            why = f"Forecast {self.message.FirstSliceStart} does not cover the next {FORECAST_HOURS} hours"
        if self.template is None or self.template.LocationAlias != self.bundle.LocationAlias:
            self.template = await self.pull_template(session, self.bundle.LocationAlias, now_s)
        if self.template is None:
            self.logger.warning(
                f"{why}, and no seasonal template for {self.bundle.LocationAlias} stored or reachable; no forecast"
            )
            return None
        self.logger.warning(f"{why}; filling from the seasonal template")
        return seasonal_fill(self.bundle, self.template, now_s)

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
                    self.logger.warning(f"Forecast pull {url} returned {response.status}")
                    return None
                message = GwWeatherForecast.model_validate(await response.json())
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            self.logger.warning(f"Forecast pull {url} failed: {e!r}")
            return None
        self.forecast_file.write_text(message.model_dump_json(by_alias=True, indent=2))
        self.logger.info(
            f"Pulled a {len(message.TempValues)}-slice {message.Fidelity.value} forecast "
            f"starting {message.FirstSliceStart}"
        )
        return message

    async def pull_bundle(self, session: aiohttp.ClientSession) -> Optional[WeatherForecastBundleGt]:
        url = f"{self.api_url}/bundles"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    self.logger.warning(f"Bundle pull {url} returned {response.status}")
                    return None
                records = [WeatherForecastBundleGt.model_validate(d) for d in await response.json()]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            self.logger.warning(f"Bundle pull {url} failed: {e!r}")
            return None
        mine = [r for r in records if r.Name == self.bundle_name]
        if not mine:
            self.logger.warning(f"The weather service has no bundle {self.bundle_name}")
            return None
        self.bundle_file.write_text(mine[0].model_dump_json(by_alias=True, indent=2))
        return mine[0]

    async def pull_template(
        self, session: aiohttp.ClientSession, location_alias: LeftRightDotStr, now_s: float
    ) -> Optional[WeatherSeasonalTemplateGt]:
        """The location's template with the latest Start at or before plant
        time `now_s`, kept in the config dir."""
        url = f"{self.api_url}/seasonal-templates"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    self.logger.warning(f"Seasonal template pull {url} returned {response.status}")
                    return None
                records = [WeatherSeasonalTemplateGt.model_validate(d) for d in await response.json()]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            self.logger.warning(f"Seasonal template pull {url} failed: {e!r}")
            return None
        mine = [r for r in records if r.LocationAlias == location_alias and utc_seconds(r.Start) <= now_s]
        if not mine:
            self.logger.warning(f"The weather service has no seasonal template for {location_alias}")
            return None
        template = max(mine, key=lambda r: r.Start)
        self.template_file(location_alias).write_text(template.model_dump_json(by_alias=True, indent=2))
        return template

    def stored_template(self, location_alias: LeftRightDotStr) -> Optional[WeatherSeasonalTemplateGt]:
        path = self.template_file(location_alias)
        if not path.exists():
            return None
        try:
            return WeatherSeasonalTemplateGt.model_validate_json(path.read_text())
        except ValidationError as e:
            self.logger.warning(f"Stored seasonal template {path} does not decode: {e!r}")
            return None

    def stored_forecast(self) -> Optional[GwWeatherForecast]:
        if not self.forecast_file.exists():
            return None
        try:
            return GwWeatherForecast.model_validate_json(self.forecast_file.read_text())
        except ValidationError as e:
            self.logger.warning(f"Stored forecast {self.forecast_file} does not decode: {e!r}")
            return None

    def stored_bundle(self) -> Optional[WeatherForecastBundleGt]:
        if not self.bundle_file.exists():
            return None
        try:
            return WeatherForecastBundleGt.model_validate_json(self.bundle_file.read_text())
        except ValidationError as e:
            self.logger.warning(f"Stored bundle record {self.bundle_file} does not decode: {e!r}")
            return None


SIM_LOCATION = "sim.millinocket"
SIM_BUNDLE_NAME = f"{SIM_LOCATION}.forecast.sim.hourly96"
SIM_SLICES = 96
SIM_FORECASTER = "sim.forecaster"
SIM_METHOD = "sim.steady"


def sim_bundle(start_s: float) -> WeatherForecastBundleGt:
    """A 96-hour hourly bundle record for the simulated weather source,
    starting at the whole hour after `start_s`, °F x100 and mph x1000 like
    the Millinocket one."""
    start = utc_iso(next_whole_hour_s(start_s))

    def observation(name: str, display: str, quantity: Quantity, unit: Unit) -> WeatherChannelGt:
        return WeatherChannelGt(
            Name=f"{SIM_LOCATION}.{name}",
            DisplayName=display,
            Quantity=quantity,
            Unit=unit,
            LocationAlias=SIM_LOCATION,
            EmitPeriodS=3600,
            EmitOffsetS=0,
            Start=start,
            Id=str(uuid.uuid4()),
        )

    def forecast_channel(name: str) -> WeatherForecastChannelGt:
        return WeatherForecastChannelGt(
            Name=f"{SIM_LOCATION}.{name}.forecast.sim.hourly96",
            TargetChannelName=f"{SIM_LOCATION}.{name}",
            Forecaster=SIM_FORECASTER,
            Method=SIM_METHOD,
            TotalSlices=SIM_SLICES,
            SliceDurationSList=[3600] * SIM_SLICES,
            ForecastDurationMinutes=SIM_SLICES * 60,
            Start=start,
            Id=str(uuid.uuid4()),
        )

    return WeatherForecastBundleGt(
        Name=SIM_BUNDLE_NAME,
        DisplayName="Simulated hourly 96-hour forecast bundle",
        LocationAlias=SIM_LOCATION,
        TempForecastChannel=forecast_channel("temperature"),
        TempObservationChannel=observation(
            "temperature", "Simulated outdoor air temperature", Quantity.Temperature, Unit.FahrenheitX100
        ),
        WindSpeedForecastChannel=forecast_channel("windspeed"),
        WindSpeedObservationChannel=observation(
            "windspeed", "Simulated wind speed", Quantity.WindSpeed, Unit.MilesPerHourX1000
        ),
        EmitPeriodS=3600,
        EmitOffsetS=60,
        Start=start,
        Id=str(uuid.uuid4()),
    )


def sim_forecast(
    now_s: float,
    oat_f: float = 30.0,
    wind_speed_mph: float = 5.0,
    bundle: Optional[WeatherForecastBundleGt] = None,
) -> ForecastPair:
    """A steady Live forecast on the simulated bundle: every slice from the
    whole hour after plant time `now_s` at `oat_f` and `wind_speed_mph`."""
    bundle = sim_bundle(now_s) if bundle is None else bundle
    slices = bundle.TempForecastChannel.TotalSlices
    message = forecast_on(
        bundle,
        WeatherForecastFidelity.Live,
        next_whole_hour_s(now_s),
        [oat_f] * slices,
        [wind_speed_mph] * slices,
        now_s,
    )
    return ForecastPair(message, bundle)


class SimWeatherSource(WeatherSource):
    """A steady 30 F and 5 mph on the simulated bundle from the plant's
    next whole hour, returned after a wall-clock delay the test sets (the
    delay stands in for a slow service, so it is IO time)."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.delay_s: float = 0
        self.bundle = sim_bundle(clock.now())

    async def forecast(self, session: aiohttp.ClientSession) -> Optional[ForecastPair]:
        await asyncio.sleep(self.delay_s)
        return sim_forecast(self.clock.now(), bundle=self.bundle)


def build_weather_source(
    kind: WeatherSourceKind,
    ops: OperationalParams,
    config_dir: Path,
    api_url: str,
    timeout_s: float,
    clock: Clock,
    base_log_name: str,
) -> WeatherSource:
    """The weather source the settings ask for, on the bundle the ops word
    names, reading plant time from the scada's clock and logging under its
    base logger."""
    if kind == WeatherSourceKind.Gwwf:
        return GwwfWeatherSource(
            ops.WeatherBundleName,
            api_url,
            config_dir,
            timeout_s,
            clock,
            logging.getLogger(f"{base_log_name}.weather_source"),
        )
    if kind == WeatherSourceKind.Sim:
        return SimWeatherSource(clock)
    raise ValueError(f"Unknown weather source {kind}")
