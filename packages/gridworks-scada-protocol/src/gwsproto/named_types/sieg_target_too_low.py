"""Type sieg.target.too.low, version 000"""

from typing import Literal


from gwproto.property_format import  LeftRightDotStr, UTCMilliseconds
from pydantic import BaseModel, StrictInt


class SiegTargetTooLow(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    TargetLwtFx10: StrictInt
    SiegColdFx10: StrictInt
    HeatPumpDeltaTx10: StrictInt
    TimeMs: UTCMilliseconds
    TypeName: Literal["sieg.target.too.low"] = "sieg.target.too.low"
    Version: str = "000"
