from typing import Literal

from gwsproto.property_format import SpaceheatName
from pydantic import BaseModel


class SuitUp(BaseModel):
    """ """

    ToNode: SpaceheatName
    FromNode: SpaceheatName
    TypeName: Literal["suit.up"] = "suit.up"
    Version: Literal["000"] = "000"
