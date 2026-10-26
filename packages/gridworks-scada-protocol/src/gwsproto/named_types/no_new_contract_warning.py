from typing import Literal

from gwsproto.property_format import LeftRightDotStr, UUID4Str, UTCSeconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class NoNewContractWarning(GwsprotoSemaType):
    FromGNodeAlias: LeftRightDotStr
    ContractId: UUID4Str
    GraceEndTimeS: UTCSeconds
    TypeName: Literal["no.new.contract.warning"] = "no.new.contract.warning"
    Version: Literal["000"] = "000"
