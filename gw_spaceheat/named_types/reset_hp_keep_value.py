"""Type reset.hp.keep.value, version 000"""
import time
from typing import Literal

from gwproto.property_format import HandleName, UTCMilliseconds
from pydantic import BaseModel, Field, PositiveInt


class ResetHpKeepValue(BaseModel):
    """
    Used to change the HpKeep percent - an integrated integer value meant to represent the 
    position of the Siegenthaler Valve from 0 ("fully send") to 100 ("fully keep") - 
    WITHOUT changing the valve
    """
    FromHandle: HandleName
    ToHandle: HandleName
    FromValue: PositiveInt
    ToValue: PositiveInt
    CreatedMs: UTCMilliseconds = Field(default_factory=lambda: int(time.time() * 1000))
    TypeName: Literal["reset.hp.keep.value"] = "reset.hp.keep.value"
    Version: Literal["000"] = "000"
