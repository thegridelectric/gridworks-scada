from typing import List, Literal
from typing_extensions import Self
from pydantic import BaseModel, model_validator

from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit
from gwsproto.property_format import LeftRightDotStr, MarketSlotName
from gwsproto.named_types.price_quantity_unitless import PriceQuantityUnitless


class AtnBid(BaseModel):
    BidderAlias: LeftRightDotStr
    MarketSlotName: MarketSlotName
    PqPairs: List[PriceQuantityUnitless]
    InjectionIsPositive: bool
    PriceUnit: MarketPriceUnit
    QuantityUnit: MarketQuantityUnit
    SignedMarketFeeTxn: str
    TypeName: Literal["atn.bid"] = "atn.bid"
    Version: Literal["002"] = "002"

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
