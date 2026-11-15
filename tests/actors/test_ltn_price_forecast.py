"""The LTN reads its request's prices off the price forecast word: the
slots from the request's own, in USD/MWh."""

import pytest

from actors.ltn.flo_request import PriceForecastMissesSlot, price_usd_mwh_from
from gwsproto.enums import MarketPriceUnit, MarketProductName
from gwsproto.named_types import PriceForecast

H = 3600
START = 1_762_178_400  # an hour boundary


def forecast(hours: int) -> PriceForecast:
    return PriceForecast(
        FromGNodeAlias="d1.price",
        MarketMakerAlias="d1.isone.ct.newhaven",
        ProductName=MarketProductName.rt60gate5,
        ForecastUid="0b6f4c1e-5a3d-4e9b-8f27-6c1d2e3f4a5b",
        CreatedMs=START * 1000,
        SlotStartS=[START + i * H for i in range(hours)],
        PriceUnit=MarketPriceUnit.USDPerMWh,
        PriceX1000List=[100_000 + 1000 * i for i in range(hours)],
    )


def test_the_prices_run_from_the_requests_slot() -> None:
    assert price_usd_mwh_from(forecast(5), START + 2 * H) == [102.0, 103.0, 104.0]


def test_the_first_slot_gives_the_whole_forecast() -> None:
    assert price_usd_mwh_from(forecast(3), START) == [100.0, 101.0, 102.0]


def test_a_slot_the_forecast_lacks_is_refused() -> None:
    with pytest.raises(PriceForecastMissesSlot, match="no slot starting at"):
        price_usd_mwh_from(forecast(3), START + 3 * H)
    with pytest.raises(PriceForecastMissesSlot, match="no slot starting at"):
        price_usd_mwh_from(forecast(3), START - H)

