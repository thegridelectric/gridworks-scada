"""Tests price.quantity.unitless type, version 000"""

from gwsproto.named_types import PriceQuantityUnitless


def test_price_quantity_unitless_generated() -> None:
    d = {
        "PriceTimes1000": 40000,
        "QuantityTimes1000": 10000,
        "TypeName": "price.quantity.unitless",
        "Version": "000",
    }

    d2 = PriceQuantityUnitless.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
