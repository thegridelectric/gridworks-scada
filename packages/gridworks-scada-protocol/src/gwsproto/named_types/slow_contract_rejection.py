from typing import Literal

from gwsproto.enums import TaValidationState
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SlowContractRejection(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/slow.contract.rejection/000"""

    FromGNodeAlias: LeftRightDotStr
    ContractId: UUID4Str
    ValidationState: TaValidationState
    MessageCreatedMs: UTCMilliseconds
    TypeName: Literal["slow.contract.rejection"] = "slow.contract.rejection"
    Version: Literal["000"] = "000"
