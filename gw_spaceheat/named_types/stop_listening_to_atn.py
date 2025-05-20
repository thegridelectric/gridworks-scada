"""Type stop.listening.to.atn, version 000"""

from typing import Literal
from gwproto.property_format import LeftRightDotStr
from pydantic import BaseModel


class StopListeningToAtn(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    TypeName: Literal["stop.listening.to.atn"] = "stop.listening.to.atn"
    Version: Literal["000"] = "000"
