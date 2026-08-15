import time
from typing import Literal

from pydantic import PositiveInt, Field

from gwsproto.property_format import HandleName, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SetLwtControlParams(GwsprotoSemaType):
    FromHandle: HandleName
    ToHandle: HandleName
    ProportionalGain: float
    IntegralGain: float
    DerivativeGain: float
    ControlIntervalSeconds: PositiveInt
    T1: PositiveInt
    T2: PositiveInt
    CreatedMs:  UTCMilliseconds = Field(default_factory=lambda: int(time.time() * 1000))
    TypeName: Literal["set.lwt.control.params"] = "set.lwt.control.params"
    Version: Literal["000"] = "000"