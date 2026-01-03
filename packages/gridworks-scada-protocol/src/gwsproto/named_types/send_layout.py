from typing import Literal

from pydantic import BaseModel

from gwsproto.property_format import LeftRightDotStr, SpaceheatName


class SendLayout(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    FromName: SpaceheatName
    ToName: SpaceheatName
    TypeName: Literal["send.layout"] = "send.layout"
    Version: Literal["000"] = "000"
