"""Type atn.bid, version 001"""

from typing import List, Literal

from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit
from gwproto.property_format import LeftRightDotStr, MarketSlotName
from gwsproto.named_types.price_quantity_unitless import PriceQuantityUnitless
from pydantic import BaseModel, field_validator, model_validator
from typing_extensions import Self


class AtnBid(BaseModel):
    BidderAlias: LeftRightDotStr
    MarketSlotName: MarketSlotName
    PqPairs: List[PriceQuantityUnitless]
    InjectionIsPositive: bool
    PriceUnit: MarketPriceUnit
    QuantityUnit: MarketQuantityUnit
    SignedMarketFeeTxn: str
    TypeName: Literal["atn.bid"] = "atn.bid"
    Version: str = "001"

    @field_validator("SignedMarketFeeTxn")
    @classmethod
    def _check_signed_market_fee_txn(cls, v: str) -> str:
        # supposed to be check_is_algo_msg_pack_encoded, hacked out in sacda
        return v

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
