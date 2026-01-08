from typing import List, Literal
from pydantic import BaseModel
from gwsproto.property_format import SpaceheatName


class MicroVolts(BaseModel):
    HwUid: str
    AboutNodeNameList: List[SpaceheatName]
    MicroVoltsList: List[int]
    TypeName: Literal["microvolts"] = "microvolts"
    Version: Literal["100"] = "100"
