"""The LTN's saved price forecast is read as seen at the plant clock's now:
hours already begun are dropped, and a short forecast repeats its last hour."""

import pytest

from actors.ltn.ltn import FORECAST_HOURS, price_forecast_from

H = 3600
START = 1_762_178_400  # an hour boundary


def rows(hours: int) -> tuple[list[float], list[float], list[float]]:
    timestamps = [float(START + i * H) for i in range(hours)]
    dp = [10.0 + i for i in range(hours)]
    lmp = [100.0 + i for i in range(hours)]
    return timestamps, dp, lmp


def test_hours_already_begun_are_dropped() -> None:
    timestamps, dp, lmp = rows(FORECAST_HOURS + 3)
    forecast = price_forecast_from(timestamps, dp, lmp, now_s=START + 2 * H + 1)
    assert forecast.dp_usd_per_mwh[:2] == [13.0, 14.0]
    assert forecast.lmp_usd_per_mwh[:2] == [103.0, 104.0]
    assert len(forecast.dp_usd_per_mwh) == FORECAST_HOURS


def test_a_row_at_now_exactly_is_already_begun() -> None:
    timestamps, dp, lmp = rows(FORECAST_HOURS + 1)
    forecast = price_forecast_from(timestamps, dp, lmp, now_s=START)
    assert forecast.dp_usd_per_mwh[0] == 11.0


def test_a_short_forecast_repeats_its_last_hour() -> None:
    timestamps, dp, lmp = rows(5)
    forecast = price_forecast_from(timestamps, dp, lmp, now_s=START - 1)
    assert len(forecast.dp_usd_per_mwh) == FORECAST_HOURS
    assert forecast.dp_usd_per_mwh[:5] == dp
    assert forecast.dp_usd_per_mwh[5:] == [dp[-1]] * (FORECAST_HOURS - 5)
    assert forecast.lmp_usd_per_mwh[5:] == [lmp[-1]] * (FORECAST_HOURS - 5)


def test_a_forecast_entirely_in_the_past_is_refused() -> None:
    timestamps, dp, lmp = rows(5)
    with pytest.raises(ValueError, match="No forecasts available"):
        price_forecast_from(timestamps, dp, lmp, now_s=START + 5 * H)
