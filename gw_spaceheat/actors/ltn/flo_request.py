"""The LTN's request to its FLO: one flo.params built from the house's
facts (the ops word, the layout's water store, the operating status, the
forecast and the store's measured state)."""

import json
from pathlib import Path
from typing import NamedTuple, Optional, Sequence

from gwsproto.enums import SeasonalStorageMode, WeatherForecastFidelity
from gwsproto.named_types import (
    FloOptimalPath,
    FloParams,
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

WATER_KWH_PER_KG_K = 4.184 / 3600
RSWT_RADIATOR_EXPONENT = 1.3


def celsius_to_fahrenheit(celsius: float) -> float:
    return celsius * (9.0 / 5.0) + 32.0


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    return (fahrenheit - 32.0) * (5.0 / 9.0)


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


class PreviousRun(NamedTuple):
    """The path the previous run's cleared price led to, with the price
    that run forecast for the slot after it. No word states the pair yet;
    a `flo.previous.run` word retires the file form below."""

    path: FloOptimalPath
    elec_usd_mwh_now: float

    def ends_at(self) -> int:
        """When the path's first step ends: the start of the slot the run
        is the previous run for."""
        return self.path.StartUnixS + self.path.StepDurationMinutes[0] * 60


def previous_run_for(run: Optional[PreviousRun], start_unix_s: int) -> Optional[PreviousRun]:
    """The run when its first step ends at `start_unix_s`, else nothing: a
    run from any other slot is no previous run for this one."""
    if run is None or run.ends_at() != start_unix_s:
        return None
    return run


def save_previous_run(file: Path, run: PreviousRun) -> None:
    """The run on disk, the path as its word."""
    file.write_text(
        json.dumps({"Path": run.path.model_dump(by_alias=True), "ElecUsdMwhNow": run.elec_usd_mwh_now})
    )


def load_previous_run(file: Path) -> Optional[PreviousRun]:
    """The run saved by `save_previous_run`, or nothing when there is none."""
    if not file.exists():
        return None
    data = json.loads(file.read_text())
    return PreviousRun(
        path=FloOptimalPath.model_validate(data["Path"]), elec_usd_mwh_now=float(data["ElecUsdMwhNow"])
    )


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


def baseline_load_kwh(curve: HeatingCurve, weather: HourlyForecast) -> list[float]:
    alpha = curve.BaselineAlphaTimes10 / 10
    beta = curve.BaselineBetaTimes100 / 100
    gamma = curve.BaselineGammaEx6 / 1e6
    return [
        max(0.0, alpha + beta*oat + gamma*ws*(65-oat))
        for oat, ws in zip(weather.oat_f, weather.wind_speed_mph, strict=True)
    ]


def load_forecast_kwh(
    curve: HeatingCurve,
    weather: HourlyForecast,
    t_room_f: float,
    last_four_dist_kwh: list[tuple[int, float | None] | None],
    last_four_oat_f: list[tuple[int, float | None] | None],
) -> list[float]:
    """Forecast of the house's hourly heat load from the regression model."""
    dist_kwh: list[float | None] = [None if item is None else item[1] for item in last_four_dist_kwh][-4:]
    oat_f: list[float | None] = [None if item is None else item[1] for item in last_four_oat_f][-4:]
    
    if not any(value is not None for value in dist_kwh) or not any(value is not None for value in oat_f):
        load = baseline_load_kwh(curve, weather)
    else:
        alpha = curve.AlphaEx6 / 1e6
        beta = curve.BetaEx6 / 1e6
        gamma = curve.GammaEx6 / 1e6
        delta = curve.DeltaEx6 / 1e6
        epsilon = curve.EpsilonEx6 / 1e6
        zeta = curve.ZetaEx6 / 1e6
        eta = curve.EtaEx6 / 1e6
        energy_ratio = curve.RhoTimes100 / 100
        
        load_window: list[float | None] = [None if value is None else energy_ratio * value for value in dist_kwh]
        oat_window: list[float | None] = oat_f
        
        load = []
        for oat, ws in zip(weather.oat_f, weather.wind_speed_mph, strict=True):
            deltaT = max(0, t_room_f - oat)
            solar_w_m2 = 0 # TODO: put solar in weather forecast
            known_load = [value for value in load_window if value is not None]
            prev_load = known_load[-1]
            prev_load_average_4_hours = sum(known_load) / len(known_load)
            known_oat = [value for value in oat_window if value is not None]
            prev_oat_average_4_hours = sum(known_oat) / len(known_oat) if known_oat else 0.0
            load.append(
                max(
                    0,
                    alpha
                    + beta * deltaT
                    + gamma * ws * deltaT
                    + delta * solar_w_m2
                    + epsilon * prev_oat_average_4_hours
                    + zeta * prev_load
                    + eta * prev_load_average_4_hours
                )
            )
            load_window = [*load_window, load[-1]][-4:]
            oat_window = [*oat_window, oat][-4:]
    return [round(l, 2) for l in load]


def adjust_load_for_buffer(load_kwh: list[float], buffer_available_kwh: float) -> list[float]:
    """Add/remove load from the first hours to account for the buffer's current energy."""
    load = list(load_kwh)
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
    return [round(l, 2) for l in load]


def rswt_forecast_f(curve: HeatingCurve, load_kwh: Sequence[float], t_room_f: float) -> list[float]:
    n = RSWT_RADIATOR_EXPONENT # TODO: make this a parameter?
    cp = WATER_KWH_PER_KG_K

    mdot = float(curve.MassFlowKgH)
    q_dd = float(curve.DdPowerKw)
    t_supply_dd = float(curve.DdRswtF)
    t_room_dd_f = float(curve.DdRoomTempF)

    t_supply_dd_c = fahrenheit_to_celsius(t_supply_dd)
    t_room_c = fahrenheit_to_celsius(t_room_f)
    t_room_dd_c = fahrenheit_to_celsius(t_room_dd_f)
    
    rad_scale = t_supply_dd_c - t_room_dd_c - q_dd/(2*mdot*cp)

    rswt_list_f: list[float] = []
    for q in load_kwh:
        t_supply_c = t_room_c + rad_scale * (q/q_dd)**(1/n) + q/(2*mdot*cp)
        rswt_list_f.append(round(celsius_to_fahrenheit(t_supply_c), 2))
    return rswt_list_f


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
    t_room_f: float,
    last_four_dist_kwh: list[tuple[int, float | None] | None],
    last_four_oat_f: list[tuple[int, float | None] | None],
    g_node_alias: str,
    start_unix_s: int,
    created_ms: int,
    previous: Optional[PreviousRun] = None,
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
    load = load_forecast_kwh(ops.HeatingCurve, weather, t_room_f, last_four_dist_kwh, last_four_oat_f)
    load_adjusted = adjust_load_for_buffer(load, buffer_available_kwh)
    rswt = rswt_forecast_f(ops.HeatingCurve, load, t_room_f)
    tanks_modeled = water_store.TotalStoreTanks if storage_mode is SeasonalStorageMode.AllTanks else 1
    return FloParams(
        GNodeAlias=g_node_alias,
        CreatedMs=created_ms,
        StartUnixS=start_unix_s,
        StepDurationMinutes=[STEP_MINUTES] * horizon,
        LmpUsdMwhList=[float(p) for p in lmp_usd_mwh[:horizon]],
        DistUsdMwhList=[float(p) for p in dist_usd_mwh[:horizon]],
        OatFList=[float(t) for t in weather.oat_f],
        LoadKwhList=load_adjusted,
        RswtFList=rswt,
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
        PreviousOptimalPath=previous.path if previous else None,
        PreviousEstimateElecUsdMwhNow=previous.elec_usd_mwh_now if previous else None,
        Tuning=ops.FloTuning,
    )
