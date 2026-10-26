from typing import Literal
from pydantic import field_validator

from gwsproto.property_format import LeftRightDotStr
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class DispatchContractGoLive(GwsprotoSemaType):
    """
    Triggers DispatchContract GoLive.

    Sent by the Ltn to its SCADA when they share an existing DispatchContract. If the SCADA
    is in LocalControl and gets this message, it will move into Ltn mode.
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
