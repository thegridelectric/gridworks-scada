"""Type hack.oil.off, version 000"""

from typing import Literal

from pydantic import BaseModel


class HackOilOff(BaseModel):
    TypeName: Literal["hack.oil.off"] = "hack.oil.off"
    Version: Literal["000"] = "000"
