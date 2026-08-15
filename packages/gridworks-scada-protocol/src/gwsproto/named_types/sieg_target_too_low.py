from typing import Literal

from gwsproto.property_format import  LeftRightDotStr, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from pydantic import StrictInt


class SiegTargetTooLow(GwsprotoSemaType):
    FromGNodeAlias: LeftRightDotStr
    TargetLwtFx10: StrictInt
    SiegColdFx10: StrictInt
    HeatPumpDeltaTx10: StrictInt
    TimeMs: UTCMilliseconds
    TypeName: Literal["sieg.target.too.low"] = "sieg.target.too.low"
    Version: Literal["000"] = "000"
