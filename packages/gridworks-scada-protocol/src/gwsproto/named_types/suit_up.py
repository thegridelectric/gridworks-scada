from typing import Literal

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SuitUp(GwsprotoSemaType):
    """ """

    ToNode: SpaceheatName
    FromNode: SpaceheatName
    TypeName: Literal["suit.up"] = "suit.up"
    Version: Literal["000"] = "000"
