"""Type start.listening.to.atn, version 000"""

from typing import Literal
from gwproto.property_format import LeftRightDotStr
from pydantic import BaseModel


class StartListeningToAtn(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    TypeName: Literal["start.listening.to.atn"] = "start.listening.to.atn"
    Version: Literal["000"] = "000"
