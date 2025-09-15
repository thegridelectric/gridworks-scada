"""Type suit.up, version 000"""

from typing import Literal

from gwproto.property_format import SpaceheatName
from pydantic import BaseModel


class SuitUp(BaseModel):
    """ """

    ToNode: SpaceheatName
    FromNode: SpaceheatName
    TypeName: Literal["suit.up"] = "suit.up"
    Version: Literal["000"] = "000"
