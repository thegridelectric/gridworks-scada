from typing import Literal

from pydantic import BaseModel
from gwsproto.property_format import SpaceheatName


class GoDormant(BaseModel):
    ToName: SpaceheatName
    TypeName: Literal["go.dormant"] = "go.dormant"
    Version: Literal["001"] = "001"
