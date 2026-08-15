from typing import Literal

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class GoDormant(GwsprotoSemaType):
    ToName: SpaceheatName
    TypeName: Literal["go.dormant"] = "go.dormant"
    Version: Literal["001"] = "001"
