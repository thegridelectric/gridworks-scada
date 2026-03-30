from typing import Literal

from pydantic import BaseModel

from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds


class SendLayout(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    MessageCreatedMs: UTCMilliseconds
    TypeName: Literal["send.layout"] = "send.layout"
    Version: Literal["001"] = "001"
