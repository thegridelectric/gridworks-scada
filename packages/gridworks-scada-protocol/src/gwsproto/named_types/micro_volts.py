from typing import List, Literal

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class MicroVolts(GwsprotoSemaType):
    HwUid: str
    AboutNodeNameList: List[SpaceheatName]
    MicroVoltsList: List[int]
    TypeName: Literal["microvolts"] = "microvolts"
    Version: Literal["100"] = "100"
