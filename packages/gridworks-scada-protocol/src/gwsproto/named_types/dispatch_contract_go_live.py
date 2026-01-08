from typing import Literal
from pydantic import BaseModel, field_validator

from gwsproto.property_format import LeftRightDotStr


class DispatchContractGoLive(BaseModel):
    """
    Triggers DispatchContract GoLive.

    Sent by the Atn to its SCADA when they share an existing DispatchContract. If the SCADA
    is in HomeAlone and gets this message, it will move into Atn mode.
    """

    FromGNodeAlias: LeftRightDotStr
    BlockchainSig: str
    TypeName: Literal["dispatch.contract.go.live"] = "dispatch.contract.go.live"
    Version: Literal["000"] = "000"

    @field_validator("BlockchainSig")
    @classmethod
    def _check_blockchain_sig(cls, v: str) -> str:
        # Add later check_is_algo_msg_pack_encoded(v)
        return v
