import time
from typing import Literal

from pydantic import BaseModel, Field, StrictInt

from gwsproto.property_format import HandleName, UTCMilliseconds


class ResetHpKeepValue(BaseModel):
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
