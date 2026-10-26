"""Type send.snap, version 000"""

from typing import Literal

from gwproto.property_format import (

    LeftRightDotStr,
)

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SendSnap(GwsprotoSemaType):
    FromGNodeAlias: LeftRightDotStr
    TypeName: Literal["send.snap"] = "send.snap"
    Version: str = "000"
