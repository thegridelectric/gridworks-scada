"""Type hack.oil.on, version 000"""

from typing import Literal

from pydantic import BaseModel


class HackOilOn(BaseModel):
    TypeName: Literal["hack.oil.on"] = "hack.oil.on"
    Version: str = "000"
