"""gw.price.forecast 000: the twin agrees with the snapshot on the word's
example and refuses each axiom clause's violation."""

import copy

from gwsproto.named_types import PriceForecast
from tests.named_types.sema_oracle import assert_conforms, assert_refused

EXAMPLE = {
    "FromGNodeAlias": "hw1.price",
    "MarketMakerAlias": "hw1.isone.me.versant.keene",
    "ProductName": "rt60gate5",
    "ForecastUid": "0b6f4c1e-5a3d-4e9b-8f27-6c1d2e3f4a5b",
    "CreatedMs": 1794420660000,
    "SlotStartS": [1794423600, 1794427200, 1794430800],
    "PriceUnit": "USDPerMWh",
    "PriceX1000List": [628052, 99876, 98806],
    "TypeName": "gw.price.forecast",
    "Version": "000",
}


def example() -> dict:
    return copy.deepcopy(EXAMPLE)


def test_example_conforms() -> None:
    assert_conforms(PriceForecast.model_validate(example()))


def test_gw_price_forecast_axiom_1_a_slots_non_empty() -> None:
    d = example()
    d["SlotStartS"] = []
    d["PriceX1000List"] = []
    assert_refused(PriceForecast, d, match="Axiom 1 \\(SlotGrid\\) clause a")


def test_gw_price_forecast_axiom_1_b_slots_strictly_ascend() -> None:
    d = example()
    d["SlotStartS"] = [1794423600, 1794423600, 1794430800]
    assert_refused(PriceForecast, d, match="Axiom 1 \\(SlotGrid\\) clause b")


def test_gw_price_forecast_axiom_1_c_slots_on_the_grid() -> None:
    d = example()
    d["SlotStartS"] = [1794423600, 1794427201, 1794430800]
    assert_refused(PriceForecast, d, match="Axiom 1 \\(SlotGrid\\) clause c")


def test_gw_price_forecast_axiom_2_one_price_per_slot() -> None:
    d = example()
    d["PriceX1000List"] = [628052, 99876]
    assert_refused(PriceForecast, d, match="Axiom 2 \\(OnePricePerSlot\\)")
