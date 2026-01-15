from typing import List, Literal
from typing_extensions import Self
from pydantic import BaseModel, model_validator

from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit
from gwsproto.property_format import LeftRightDotStr, MarketSlotName
from gwsproto.named_types.price_quantity_unitless import PriceQuantityUnitless


class Bid(BaseModel):
    """ASL: https://schemas.electricity.works/types/bid/000"""

    BidderAlias: LeftRightDotStr
    MarketSlotName: MarketSlotName
    PqPairs: List[PriceQuantityUnitless]
    InjectionIsPositive: bool
    PriceUnit: MarketPriceUnit
    QuantityUnit: MarketQuantityUnit
    SignedMarketFeeTxn: str
    TypeName: Literal["bid"] = "bid"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Market normalization anchor.

        The first price of the first PriceQuantity pair in PqPairs SHALL equal
        the PriceMax defined by the MarketType associated with MarketSlotName.
        """
        # Implement check for axiom 1"
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: Unit consistency.

        PriceUnit and QuantityUnit SHALL match the units declared by the
        MarketType associated with MarketSlotName.
        """
        # Implement check for axiom 1"
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: Curve admissibility

        The structure, ordering, and cardinality of PqPairs SHALL conform to
        the admissibility rules of the MarketType associated with MarketSlotName
        (including any constraints on price ordering, monotonicity, tick size,
        or maximum number of segments).
        """
        # Implement check for axiom 2"
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: Economic admission.

        SignedMarketFeeTxn MUST be verifiable under the market’s fee and
        admission policy for the specified MarketSlot.
        """
        # Implement check for axiom 4"
        return self
