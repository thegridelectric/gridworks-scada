"""Type dispatch.contract.go.dormant, version 000"""

from typing import Literal

from gwproto.property_format import LeftRightDotStr
from pydantic import BaseModel, field_validator


class DispatchContractGoDormant(BaseModel):
    """ """

    FromGNodeAlias: LeftRightDotStr
    BlockchainSig: str
    TypeName: Literal["dispatch.contract.go.dormant"] = "dispatch.contract.go.dormant"
    Version: Literal["000"] = "000"

    @field_validator("BlockchainSig")
    @classmethod
    def _check_blockchain_sig(cls, v: str) -> str:
        # Add later: check_is_algo_msg_pack_encoded(v)
        return v
