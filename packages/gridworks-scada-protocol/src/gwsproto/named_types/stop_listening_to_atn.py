from typing import Literal
from gwsproto.property_format import LeftRightDotStr
from pydantic import BaseModel


class StopListeningToAtn(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    TypeName: Literal["stop.listening.to.atn"] = "stop.listening.to.atn"
    Version: Literal["000"] = "000"
