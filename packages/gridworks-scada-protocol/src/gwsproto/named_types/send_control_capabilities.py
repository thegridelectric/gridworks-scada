from typing import Literal

from pydantic import BaseModel

from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds


class SendControlCapabilities(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    MessageCreatedMs: UTCMilliseconds
    TypeName: Literal["send.control.capabilities"] = "send.control.capabilities"
    Version: Literal["000"] = "000"
