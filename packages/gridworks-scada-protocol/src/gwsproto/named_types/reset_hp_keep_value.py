import time
from typing import Literal

from pydantic import Field, StrictInt

from gwsproto.property_format import HandleName, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ResetHpKeepValue(GwsprotoSemaType):
    """
    Used to change the HpKeepSeconds - an integrated value meant to represent the 
    position of the Siegenthaler Valve from 0 ("fully send") to 100 ("fully keep") - 
    WITHOUT changing the valve
    """
    FromHandle: HandleName
    ToHandle: HandleName
    HpKeepSecondsTimes10: StrictInt
    CreatedMs: UTCMilliseconds = Field(default_factory=lambda: int(time.time() * 1000))
    TypeName: Literal["reset.hp.keep.value"] = "reset.hp.keep.value"
    Version: Literal["001"] = "001"
