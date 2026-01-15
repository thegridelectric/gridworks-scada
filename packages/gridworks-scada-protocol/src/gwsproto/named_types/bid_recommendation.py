from typing import Literal, Self

from pydantic import BaseModel, model_validator

from gwsproto.property_format import LeftRightDotStr, MarketSlotName

from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit
from gwsproto.named_types.price_quantity_unitless import PriceQuantityUnitless


class BidRecommendation(BaseModel):
    BidderAlias: LeftRightDotStr
    MarketSlotName: MarketSlotName
    PqPairs: list[PriceQuantityUnitless]
    PqPairsWithOilBoiler: list[PriceQuantityUnitless]
    InjectionIsPositive: bool
    PriceUnit: MarketPriceUnit
    QuantityUnit: MarketQuantityUnit
    TypeName: Literal["bid.recommendation"] = "bid.recommendation"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: PqPairs PriceMax matches MarketType.
        There is a GridWorks global list of MarketTypes (a GridWorks type), identified by
        their MarketTypeNames (a GridWorks enum).  The MarketType has a PriceMax, which
        must be the first price of the first PriceQuantity pair in PqPairs.
        """
        # Implement check for axiom 1"
        return self

