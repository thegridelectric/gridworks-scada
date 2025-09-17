"""
Tests for enum market.quantity.unit.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import MarketQuantityUnit


def test_market_quantity_unit() -> None:
    assert set(MarketQuantityUnit.values()) == {
        "AvgMW",
        "AvgkW",
    }

    assert MarketQuantityUnit.default() == MarketQuantityUnit.AvgMW
    assert MarketQuantityUnit.enum_name() == "market.quantity.unit"
    assert MarketQuantityUnit.enum_version() == "000"
