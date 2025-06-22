"""Type wake.up, version 000"""

from typing import Literal

from gwproto.property_format import SpaceheatName
from pydantic import BaseModel


class WakeUp(BaseModel):
    ToName: SpaceheatName
    TypeName: Literal["wake.up"] = "wake.up"
    Version: Literal["000"] = "000"
