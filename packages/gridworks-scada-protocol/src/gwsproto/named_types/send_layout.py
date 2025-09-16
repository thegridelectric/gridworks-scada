"""Type send.layout, version 000"""

from typing import Literal

from gwproto.property_format import LeftRightDotStr, SpaceheatName
from pydantic import BaseModel


class SendLayout(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    FromName: SpaceheatName
    ToName: SpaceheatName
    TypeName: Literal["send.layout"] = "send.layout"
    Version: str = "000"
