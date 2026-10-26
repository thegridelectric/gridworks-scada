from typing import Literal

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class PicoMissing(GwsprotoSemaType):
    ActorName: SpaceheatName
    PicoHwUid: str
    TypeName: Literal["pico.missing"] = "pico.missing"
    Version: Literal["000"] = "000"
