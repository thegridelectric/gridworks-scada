from typing import Literal

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class WakeUp(GwsprotoSemaType):
    ToName: SpaceheatName
    TypeName: Literal["wake.up"] = "wake.up"
    Version: Literal["000"] = "000"
