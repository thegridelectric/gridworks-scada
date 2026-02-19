from typing import Literal

from gwsproto.property_format import SpaceheatName
from pydantic import BaseModel


class WakeUp(BaseModel):
    ToName: SpaceheatName
    TypeName: Literal["wake.up"] = "wake.up"
    Version: Literal["000"] = "000"
