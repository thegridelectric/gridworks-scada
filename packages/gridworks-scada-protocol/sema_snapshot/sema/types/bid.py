from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import MarketPriceUnit
from sema_snapshot.sema.enums import MarketQuantityUnit
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import MarketSlotName
from sema_snapshot.sema.types.price_quantity_unitless import PriceQuantityUnitless


class Bid(SemaType):
    """Sema: https://schemas.electricity.works/types/bid/000"""

    bidder_alias: LeftRightDot
    market_slot_name: MarketSlotName
    pq_pairs: list[PriceQuantityUnitless]
    injection_is_positive: bool
    price_unit: MarketPriceUnit
    quantity_unit: MarketQuantityUnit
    signed_market_fee_txn: str
    type_name: Literal["bid"] = "bid"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "Bid":
        """
        Axiom 1: MarketNormalizationAnchor
        The price of the first element in PqPairs SHALL equal the PriceMax defined by the
        MarketType associated with MarketSlotName.
        """
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "Bid":
        """
        Axiom 2: UnitConsistency
        PriceUnit and QuantityUnit SHALL match the units declared by the MarketType associated
        with MarketSlotName.
        """
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "Bid":
        """
        Axiom 3: CurveAdmissibility
        The structure, ordering, and cardinality of PqPairs SHALL conform to the admissibility
        rules of the MarketType associated with MarketSlotName (including any constraints on
        price ordering, monotonicity, tick size, or maximum number of segments).
        """
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "Bid":
        """
        Axiom 4: EconomicAdmission
        SignedMarketFeeTxn MUST be verifiable under the market’s fee and admission policy for
        the specified MarketSlot.
        """
        return self
