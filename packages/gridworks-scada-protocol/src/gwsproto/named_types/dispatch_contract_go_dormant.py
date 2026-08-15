from typing import Literal

from gwsproto.property_format import LeftRightDotStr
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from pydantic import field_validator


class DispatchContractGoDormant(GwsprotoSemaType):
    FromGNodeAlias: LeftRightDotStr
    BlockchainSig: str
    TypeName: Literal["dispatch.contract.go.dormant"] = "dispatch.contract.go.dormant"
    Version: Literal["000"] = "000"

    @field_validator("BlockchainSig")
    @classmethod
    def _check_blockchain_sig(cls, v: str) -> str:
        # Add later: check_is_algo_msg_pack_encoded(v)
        return v
