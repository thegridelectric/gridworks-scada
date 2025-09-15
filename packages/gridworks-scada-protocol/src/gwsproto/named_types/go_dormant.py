"""Type go.dormant, version 000"""

from typing import Literal
from gwproto.property_format import SpaceheatName
from pydantic import BaseModel


class GoDormant(BaseModel):
    ToName: SpaceheatName
    TypeName: Literal["go.dormant"] = "go.dormant"
    Version: Literal["001"] = "001"
