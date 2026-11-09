"""The LTN's request to its FLO: one flo.params built from the house's
facts (the ops word, the layout's water store, the operating status, the
forecast and the store's measured state)."""

from pathlib import Path
from typing import NamedTuple, Optional, Sequence

import numpy as np

from gwsproto.enums import SeasonalStorageMode, WeatherForecastFidelity
from gwsproto.named_types import (
    FloParams,
    FloPreviousRun,
    HeatingCurve,
    OperationalParams,
    WaterStore,
)
from actors.ltn.market import MARKET_SLOT_S
from weather_source import FORECAST_HOURS, ForecastPair, HourlyForecast

MAX_HORIZON_HOURS = 48
STEP_MINUTES = 60

# The market's price bounds. No word states them yet; the MarketMaker's
# product word retires these two constants.
PRICE_MAX_USD_MWH = 2000.0
PRICE_MIN_USD_MWH = -100.0


class SeasonalFillForecast(ValueError):
    """The forecast pair is a seasonal fill, so the LTN runs no FLO on it."""


class StoreState(NamedTuple):
    """The store as measured when the request is built: the three-layer
    temperatures, the thermoclines as sensor-layer counts from the top,
    and whether the heat pump is running."""

    top_f: float
    middle_f: float
    bottom_f: float
    thermocline1: int
    thermocline2: int
    hp_on: bool


def previous_run_ends_at(run: FloPreviousRun) -> int:
    """When the run's path's first step ends: the start of the slot the run
    is the previous run for."""
    return run.Path.StartUnixS + run.Path.StepDurationMinutes[0] * 60


def previous_run_for(run: Optional[FloPreviousRun], start_unix_s: int) -> Optional[FloPreviousRun]:
    """The run when its first step ends at `start_unix_s`, else nothing: a
    run from any other slot is no previous run for this one."""
    if run is None or previous_run_ends_at(run) != start_unix_s:
        return None
    return run


def previous_price_usd_mwh(run: FloPreviousRun) -> float:
    """The run's next-slot price as the request states it: USD per MWh."""
    return run.NextSlotPriceX1000 / 1000


def save_previous_run(file: Path, run: FloPreviousRun) -> None:
    """The run on disk as its word."""
    file.write_text(run.model_dump_json(by_alias=True))


def load_previous_run(file: Path) -> Optional[FloPreviousRun]:
    """The run saved by `save_previous_run`, or nothing when there is none."""
    if not file.exists():
        return None
    return FloPreviousRun.model_validate_json(file.read_text())


def next_slot_start_s(now_s: float) -> int:
    """The start of the market slot after the one `now_s` is in, in UTC
    seconds: whole slots of the epoch, so a clock change in the plant's
    timezone does not move it."""
    return (int(now_s) // MARKET_SLOT_S + 1) * MARKET_SLOT_S


def seconds_to_slot_start(now_s: float) -> int:
    """Whole seconds from `now_s` to the start of the next market slot."""
    return next_slot_start_s(now_s) - int(now_s)


def live_forecast(forecast: ForecastPair) -> ForecastPair:
    """The pair itself when every series is live or stored; a seasonal
    fill is refused."""
    filled = [s.Quantity.value for s in forecast.message.SeriesList if s.Fidelity is WeatherForecastFidelity.SeasonalTemplate]
    if filled:
        raise SeasonalFillForecast(
            f"Forecast {forecast.message.ForecastUid} on {forecast.message.BundleName} "
            f"is a seasonal fill ({', '.join(filled)})"
        )
    return forecast


def load_forecast_kwh(
    curve: HeatingCurve, weather: HourlyForecast, buffer_available_kwh: float
) -> list[float]:
    """The house's hourly heat load from the heating curve, with the
    buffer's available energy taken off the first hours (or, when the
    buffer is short, added to the first)."""
    alpha = curve.AlphaTimes10 / 10
    beta = curve.BetaTimes100 / 100
    gamma = curve.GammaEx6 / 1e6
    load = [
        max(0.0, alpha + beta * oat + gamma * ws * (65 - oat))
        for oat, ws in zip(weather.oat_f, weather.wind_speed_mph, strict=True)
    ]
    remaining = buffer_available_kwh
    if remaining < 0:
        load[0] += -remaining
    else:
        i = 0
        while remaining > 0 and i < len(load):
            taken = min(remaining, load[i])
            load[i] -= taken
            remaining -= taken
            i += 1
    return load


def rswt_forecast_f(curve: HeatingCurve, load_kwh: Sequence[float]) -> list[float]:
    """The required source water temperature per hour, from the heating
    curve's quadratic through its three power points."""
    no_power_rswt = -(curve.AlphaTimes10 / 10) / (curve.BetaTimes100 / 100)
    x_rswt = np.array([no_power_rswt, curve.IntermediateRswtF, curve.DdRswtF])
    y_power = np.array([0, curve.IntermediatePowerKw, curve.DdPowerKw])
    A = np.vstack([x_rswt**2, x_rswt, np.ones_like(x_rswt)]).T
    a, b, c = np.linalg.lstsq(A, y_power, rcond=None)[0]
    return [round((-b + (b**2 - 4 * a * (c - load)) ** 0.5) / (2 * a), 2) for load in load_kwh]


def build_flo_params(
    *,
    ops: OperationalParams,
    water_store: WaterStore,
    storage_mode: SeasonalStorageMode,
    forecast: ForecastPair,
    now_s: float,
    horizon_hours: int,
    lmp_usd_mwh: Sequence[float],
    dist_usd_mwh: Sequence[float],
    store: StoreState,
    buffer_available_kwh: float,
    g_node_alias: str,
    start_unix_s: int,
    created_ms: int,
    previous: Optional[FloPreviousRun] = None,
) -> FloParams:
    """The request for one run: the horizon is the shortest of what was
    asked, the cap, the forecast and the prices; the store modeled is the
    whole store in AllTanks and one tank in BufferOnly."""
    weather = live_forecast(forecast).next_hours(FORECAST_HOURS, now_s)
    horizon = min(horizon_hours, MAX_HORIZON_HOURS, len(weather.time), len(lmp_usd_mwh), len(dist_usd_mwh))
    weather = HourlyForecast(
        time=weather.time[:horizon],
        oat_f=weather.oat_f[:horizon],
        wind_speed_mph=weather.wind_speed_mph[:horizon],
    )
    load = load_forecast_kwh(ops.HeatingCurve, weather, buffer_available_kwh)
    tanks_modeled = water_store.TotalStoreTanks if storage_mode is SeasonalStorageMode.AllTanks else 1
    return FloParams(
        GNodeAlias=g_node_alias,
        CreatedMs=created_ms,
        StartUnixS=start_unix_s,
        StepDurationMinutes=[STEP_MINUTES] * horizon,
        LmpUsdMwhList=[float(p) for p in lmp_usd_mwh[:horizon]],
        DistUsdMwhList=[float(p) for p in dist_usd_mwh[:horizon]],
        OatFList=[float(t) for t in weather.oat_f],
        LoadKwhList=load,
        RswtFList=rswt_forecast_f(ops.HeatingCurve, load),
        WeatherForecastId=forecast.message.ForecastUid,
        SeasonalStorageMode=storage_mode,
        TanksModeled=tanks_modeled,
        GallonsPerTank=water_store.GallonsPerTank,
        TempSensorsPerTank=water_store.TempSensorsPerTank,
        MaxTankTempF=float(ops.HeatingCurve.MaxEwtF),
        InitialTopTempF=float(store.top_f),
        InitialMiddleTempF=float(store.middle_f),
        InitialBottomTempF=float(store.bottom_f),
        InitialThermocline1=store.thermocline1,
        InitialThermocline2=store.thermocline2,
        HpCurrentlyOn=store.hp_on,
        HpMaxKwEl=ops.HpMaxKwEl,
        HpTurnOnMinutes=ops.HpTurnOnMinutes,
        CopIntercept=ops.CopCurve.Intercept,
        CopOatCoeff=ops.CopCurve.OatCoeff,
        CopLwtCoeff=ops.CopCurve.LwtCoeff,
        CopMin=ops.CopCurve.Min,
        CopMinOatF=ops.CopCurve.MinOatF,
        PriceMaxUsdMwh=PRICE_MAX_USD_MWH,
        PriceMinUsdMwh=PRICE_MIN_USD_MWH,
        PreviousOptimalPath=previous.Path if previous else None,
        PreviousEstimateElecUsdMwhNow=previous_price_usd_mwh(previous) if previous else None,
        Tuning=ops.FloTuning,
    )
