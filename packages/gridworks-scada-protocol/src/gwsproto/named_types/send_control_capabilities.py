from typing import Literal

from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SendControlCapabilities(GwsprotoSemaType):
    FromGNodeAlias: LeftRightDotStr
    MessageCreatedMs: UTCMilliseconds
    TypeName: Literal["send.control.capabilities"] = "send.control.capabilities"
    Version: Literal["000"] = "000"
