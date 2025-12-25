from typing import Literal

from pydantic import BaseModel

from gwproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UUID4Str,
)

from gwsproto.enums import GwUnit


class DerivedChannelGt(BaseModel):
    Id: UUID4Str
    Name: SpaceheatName
    CreatedByNodeName: SpaceheatName
    Strategy: SpaceheatName
    OutputUnit: GwUnit | None = None
    DisplayName: str
    TerminalAssetAlias: LeftRightDotStr
    TypeName: Literal["derived.channel.gt"] = "derived.channel.gt"
    Version: str = "000"