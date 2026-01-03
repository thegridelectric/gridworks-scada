from typing import Literal
from pydantic import BaseModel, field_validator, model_validator
from typing_extensions import Self
from gw.enums import MarketTypeName
from gwsproto.property_format import UUID4Str, MarketName,MarketSlotName, LeftRightDotStr, UTCMilliseconds

class MarketMakerAck(BaseModel):
    """Acknowledgement of bid
    
    Note: While all necessary information is encoded in MarketSlotName,
    we include individual fields to improve clarity and enable explicit
    validation. The axiom check_axiom_1 ensures all fields are consistent
    with MarketSlotName.
    """
    MarketSlotName: MarketSlotName
    MarketName: MarketName
    MarketType: MarketTypeName
    MarketMakerAlias: LeftRightDotStr
    BidderAlias: LeftRightDotStr
    StartUnixS: int
    DurationMinutes: int
    ContractId: UUID4Str  # BidId from original AtnBid
    Signature: str
    AckTimeMs: UTCMilliseconds
    TypeName: Literal["market.maker.ack"] = "market.maker.ack"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1:  MarketSlotName, MarketName, MarketType, MarketMakerAlias,
        StartUnixS, and DurationMinutes are all consistent.

        MarketSlotName format is: e|r|d.{market_type}.{market_maker_alias}.{start_s}
        MarketName format is: e|r|d.{market_type}.{market_maker_alias}
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
            raise ValueError(f"MarketMakerAck consistency check failed: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error validating MarketMakerAck consistency: {str(e)}")

        return self

    @field_validator("Signature")
    @classmethod
    def _check_signature(cls, v: str) -> str:
        """
        Future: Will validate Algorand smart contract transaction signature.
        Currently accepts placeholder that follows basic Algorand message pack format.
        """
        # TODO: Replace with real Algorand transaction signature validation
        if not v.startswith("algo_sig_"):
            raise ValueError(
                "Even placeholder signatures must start with 'algo_sig_' "
                "to indicate Algorand signing intent"
            )
        return v
