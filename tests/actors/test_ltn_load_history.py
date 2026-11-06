"""The LTN's regression inputs: the four-hour histories it keeps for the
load forecast, and the two forecast functions those histories feed."""

import pytest

from actors.ltn.flo_request import baseline_load_kwh, load_forecast_kwh, rswt_forecast_f
from actors.ltn.ltn import Ltn
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatChannelNames as HCN,
)
from tests.actors.test_flo_request import AVERAGE_ZONE_TEMP_F, live_pair, ops
from weather_source import HourlyForecast, utc_seconds

HOUR_S = 3600
FORECAST_START_S = utc_seconds("2026-10-18T21:00:00Z")  # the fixture's FirstSliceStart


def bare_ltn(monkeypatch: pytest.MonkeyPatch) -> Ltn:
    ltn = Ltn.__new__(Ltn)
    monkeypatch.setattr(Ltn, "log", lambda self, note: None)
    ltn.latest_channel_values = {}
    ltn.last_four_dist_kwh = []
    ltn.last_four_oat_f = []
    ltn.weather_forecast = live_pair()
    return ltn


@pytest.mark.asyncio
async def test_four_consecutive_slots_keep_four_hours_of_dist_energy(
    monkeypatch,
) -> None:
    ltn = bare_ltn(monkeypatch)
    ltn.latest_channel_values[HCN.last_hour_dist_energy] = 2500
    slots = [FORECAST_START_S + i * HOUR_S for i in range(1, 5)]
    for slot_start_s in slots:
        await ltn.update_dist_kwh_history(slot_start_s)
    assert ltn.last_four_dist_kwh == [(s - HOUR_S, 2.5) for s in slots]


@pytest.mark.asyncio
async def test_a_fifth_slot_drops_the_oldest_hour(monkeypatch) -> None:
    ltn = bare_ltn(monkeypatch)
    ltn.latest_channel_values[HCN.last_hour_dist_energy] = 2500
    slots = [FORECAST_START_S + i * HOUR_S for i in range(1, 6)]
    for slot_start_s in slots:
        await ltn.update_dist_kwh_history(slot_start_s)
    assert [item[0] for item in ltn.last_four_dist_kwh if item] == [
        s - HOUR_S for s in slots[1:]
    ]


@pytest.mark.asyncio
async def test_oat_history_fills_when_the_forecast_starts_at_the_slot(
    monkeypatch,
) -> None:
    """The finished hour is before the forecast's first slice; the nearest
    slice stands in for it rather than leaving the hour empty."""
    ltn = bare_ltn(monkeypatch)
    await ltn.update_oat_f_history(FORECAST_START_S)
    first_slice_oat_f = ltn.weather_forecast.next_hours(1, FORECAST_START_S - 1).oat_f[
        0
    ]
    assert ltn.last_four_oat_f == [(FORECAST_START_S - HOUR_S, first_slice_oat_f)]


def test_the_design_day_anchor_returns_its_own_rswt() -> None:
    curve = ops().HeatingCurve
    assert rswt_forecast_f(curve, [curve.DdPowerKw], float(curve.DdRoomTempF)) == [
        float(curve.DdRswtF)
    ]


def test_a_full_history_leaves_the_baseline_model() -> None:
    curve = ops().HeatingCurve
    weather = HourlyForecast(
        time=[1, 2, 3], oat_f=[30.0, 30.0, 30.0], wind_speed_mph=[0.0, 0.0, 0.0]
    )
    history = [(i * HOUR_S, 2.0) for i in range(4)]
    oats = [(i * HOUR_S, 30.0) for i in range(4)]
    regression = load_forecast_kwh(curve, weather, AVERAGE_ZONE_TEMP_F, history, oats)
    assert regression != baseline_load_kwh(curve, weather)
    assert all(load >= 0 for load in regression)
    empty: list[tuple[int, float | None] | None] = []
    assert load_forecast_kwh(
        curve, weather, AVERAGE_ZONE_TEMP_F, empty, empty
    ) == baseline_load_kwh(curve, weather)
