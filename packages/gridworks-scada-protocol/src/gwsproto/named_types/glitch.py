import time
from typing import Literal

from pydantic import BaseModel, Field

from gwsproto.enums import LogLevel
from gwsproto.property_format import LeftRightDotStr, SpaceheatName, UTCMilliseconds


class Glitch(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    Node: SpaceheatName
    Type: LogLevel
    Summary: str
    Details: str
    CreatedMs: UTCMilliseconds = Field(default_factory=lambda: int(time.time() * 1000))
    TypeName: Literal["glitch"] = "glitch"
    Version: Literal["000"] = "000"
