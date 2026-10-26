"""Type ally.gives.up, version 001"""

from typing import Literal

from gwsproto.enums import DispatchRefusalReason
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class AllyGivesUp(GwsprotoSemaType):
    """The scada ends its part in dispatch. Reason is the refusal vocabulary
    the terminating heartbeat names; Cause is the particular."""

    Reason: DispatchRefusalReason
    Cause: str
    TypeName: Literal["ally.gives.up"] = "ally.gives.up"
    Version: Literal["001"] = "001"
