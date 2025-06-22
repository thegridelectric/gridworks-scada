"""Type atn.bid, version 001"""

from typing import List, Literal

from enums import MarketPriceUnit, MarketQuantityUnit, MarketTypeName
from gwproto.property_format import (LeftRightDotStr, MarketSlotName, MarketName, 
                        UUID4Str, UTCMilliseconds)
from named_types.price_quantity_unitless import PriceQuantityUnitless
from pydantic import BaseModel, field_validator, model_validator
from typing_extensions import Self


class AtnBid(BaseModel):
    """Bid from AtomicTNode to MarketMaker
    
    Note: While key information is encoded in MarketSlotName,
    we include individual fields to improve clarity and enable explicit
    validation. The axiom check_axiom_1 ensures all fields are consistent
    with MarketSlotName.
    """
    BidId: UUID4Str
    MarketSlotName: MarketSlotName
    MarketName: MarketName
    MarketType: MarketTypeName
    MarketMakerAlias: LeftRightDotStr
    BidderAlias: LeftRightDotStr
    StartUnixS: int
    DurationMinutes: int
    PqPairs: List[PriceQuantityUnitless]
    InjectionIsPositive: bool
    PriceUnit: MarketPriceUnit
    QuantityUnit: MarketQuantityUnit
    Signature: str  # Algorand signature from bidder's TaTradingRights
    BidTimeMs: UTCMilliseconds
    TypeName: Literal["atn.bid"] = "atn.bid"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: MarketSlotName, MarketName, MarketType, MarketMakerAlias,
        StartUnixS, and DurationMinutes are all consistent
        """
        try:
            # Split apart MarketSlotName
            market_slot_parts = self.MarketSlotName.split('.')
            if len(market_slot_parts) < 4:
                raise ValueError("MarketSlotName must have at least 4 parts")
            
            slot_market_service = market_slot_parts[0]  # e|r|d
            slot_market_type = market_slot_parts[1]
            slot_start_s = int(market_slot_parts[-1])
            slot_market_maker = '.'.join(market_slot_parts[2:-1])

            # Split apart MarketName 
            market_parts = self.MarketName.split('.')
            if len(market_parts) < 3:
                raise ValueError("MarketName must have at least 3 parts")
            
            market_service = market_parts[0]  # e|r|d
            market_type_str = market_parts[1]
            market_maker = '.'.join(market_parts[2:])

            # Check consistency
            if slot_market_service != market_service:
                raise ValueError(
                    f"Market service mismatch: {slot_market_service} vs {market_service}"
                )

            if slot_market_type != market_type_str:
                raise ValueError(
                    f"Market type mismatch: {slot_market_type} vs {market_type_str}"
                )

            if slot_market_type != self.MarketType.value:
                raise ValueError(
                    f"MarketType mismatch: {slot_market_type} vs {self.MarketType.value}"
                )

            if slot_market_maker != market_maker:
                raise ValueError(
                    f"Market maker mismatch: {slot_market_maker} vs {market_maker}"
                )

            if market_maker != self.MarketMakerAlias:
                raise ValueError(
                    f"MarketMakerAlias mismatch: {market_maker} vs {self.MarketMakerAlias}"
                )

            if slot_start_s != self.StartUnixS:
                raise ValueError(
                    f"StartUnixS mismatch: {slot_start_s} vs {self.StartUnixS}"
                )

            # Check that the StartUnixS aligns with market duration
            from gw.data_classes.market_type import MarketType
            market_obj = MarketType.by_id.get(self.MarketType)
            if market_obj:
                if self.DurationMinutes != market_obj.duration_minutes:
                    raise ValueError(
                        f"DurationMinutes {self.DurationMinutes} does not match "
                        f"market type {market_obj.name} duration {market_obj.duration_minutes}"
                    )
                if slot_start_s % (market_obj.duration_minutes * 60) != 0:
                    raise ValueError(
                        f"StartUnixS {slot_start_s} not aligned with "
                        f"market duration {market_obj.duration_minutes} minutes"
                    )

        except ValueError as e:
            raise ValueError(f"AtnBid consistency check failed: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error validating AtnBid consistency: {str(e)}")

        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: PqPairs are ordered by increasing price
        
        Note: For a bid to buy power (InjectionIsPositive=False), this means
        higher prices lead to lower consumption. For a bid to sell power
        (InjectionIsPositive=True), higher prices lead to higher injection.
        """
        if len(self.PqPairs) < 1:
            raise ValueError("Must have at least one PQ pair")
            
        for i in range(len(self.PqPairs) - 1):
            if self.PqPairs[i].PriceTimes1000 >= self.PqPairs[i+1].PriceTimes1000:
                raise ValueError(
                    f"PQ pairs must have strictly increasing prices. Pair {i} "
                    f"({self.PqPairs[i].PriceTimes1000}) >= Pair {i+1} "
                    f"({self.PqPairs[i+1].PriceTimes1000})"
                )
        return self

    @field_validator("Signature")
    @classmethod
    def _check_signature(cls, v: str) -> str:
        """Validates signature format
        
        Future: Will validate Algorand signature from Terminal Asset Trading Rights 
        NFT. Currently accepts placeholder that follows basic Algorand message pack
        format.
        """
        # TODO: Replace with real Algorand TaTradingRights signature validation
        if not v.startswith("algo_sig_"):
            raise ValueError(
                "Even placeholder signatures must start with 'algo_sig_' "
                "to indicate Algorand signing intent"
            )
        return v