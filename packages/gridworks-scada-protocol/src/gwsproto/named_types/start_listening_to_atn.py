from typing import Literal
from gwsproto.property_format import LeftRightDotStr
from pydantic import BaseModel


class StartListeningToAtn(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    TypeName: Literal["start.listening.to.atn"] = "start.listening.to.atn"
    Version: Literal["000"] = "000"
