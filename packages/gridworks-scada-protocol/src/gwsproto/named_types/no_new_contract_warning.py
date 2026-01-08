from typing import Literal
from pydantic import BaseModel

from gwsproto.property_format import LeftRightDotStr, UUID4Str, UTCSeconds

class NoNewContractWarning(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    ContractId: UUID4Str
    GraceEndTimeS: UTCSeconds
    TypeName: Literal["no.new.contract.warning"] = "no.new.contract.warning"
    Version: Literal["000"] = "000"
