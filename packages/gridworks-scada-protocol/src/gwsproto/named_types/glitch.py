"""Type glitch, version 000"""
import time
from typing import Literal

from gwsproto.enums import LogLevel
from gwproto.property_format import LeftRightDotStr, SpaceheatName, UTCMilliseconds
from pydantic import BaseModel, Field


class Glitch(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    Node: SpaceheatName
    Type: LogLevel
    Summary: str
    Details: str
    CreatedMs: UTCMilliseconds = Field(default_factory=lambda: int(time.time() * 1000))
    TypeName: Literal["glitch"] = "glitch"
    Version: str = "000"
