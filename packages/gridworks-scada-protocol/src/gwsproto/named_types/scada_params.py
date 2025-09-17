"""Type scada.params, version 002"""

from typing import Literal, Optional

from gwproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UTCMilliseconds,
    UUID4Str,
)
from gwsproto.named_types.ha1_params import Ha1Params
from pydantic import BaseModel, ConfigDict


class ScadaParams(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    FromName: SpaceheatName
    ToName: SpaceheatName
    UnixTimeMs: UTCMilliseconds
    MessageId: UUID4Str
    NewParams: Optional[Ha1Params] = None
    OldParams: Optional[Ha1Params] = None
    TypeName: Literal["scada.params"] = "scada.params"
    Version: str = "002"

    model_config = ConfigDict(extra="allow")
