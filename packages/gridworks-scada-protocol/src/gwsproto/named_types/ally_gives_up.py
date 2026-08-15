"""Type ally.gives.up, version 000"""

from typing import Literal

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class AllyGivesUp(GwsprotoSemaType):
    Reason: str  # This allows us to communicate why we're giving up
    TypeName: Literal["ally.gives.up"] = "ally.gives.up"
    Version: str = "000"
