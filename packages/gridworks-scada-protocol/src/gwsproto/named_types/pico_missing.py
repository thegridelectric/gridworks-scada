from typing import Literal

from gwsproto.property_format import SpaceheatName
from pydantic import BaseModel


class PicoMissing(BaseModel):
    ActorName: SpaceheatName
    PicoHwUid: str
    TypeName: Literal["pico.missing"] = "pico.missing"
    Version: Literal["000"] = "000"
