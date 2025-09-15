
"""Type set.lwt.control.params, version 000"""
import time
from typing import Literal

from gwproto.property_format import HandleName, UTCMilliseconds
from pydantic import BaseModel, PositiveInt, Field
from typing_extensions import Self


class SetLwtControlParams(BaseModel):
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