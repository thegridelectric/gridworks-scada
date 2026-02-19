"""Type send.snap, version 000"""

from typing import Literal

from pydantic import BaseModel

from gwproto.property_format import (
    LeftRightDotStr,
)


class SendSnap(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    TypeName: Literal["send.snap"] = "send.snap"
    Version: str = "000"
