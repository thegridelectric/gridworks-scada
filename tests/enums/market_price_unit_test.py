"""
Tests for enum market.price.unit.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import MarketPriceUnit


def test_market_price_unit() -> None:
    assert set(MarketPriceUnit.values()) == {
        "USDPerMWh",
    }

    assert MarketPriceUnit.default() == MarketPriceUnit.USDPerMWh
    assert MarketPriceUnit.enum_name() == "market.price.unit"
    assert MarketPriceUnit.enum_version() == "000"
