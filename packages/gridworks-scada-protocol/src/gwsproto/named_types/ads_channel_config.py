from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt

from gwsproto.enums import ThermistorDataMethod
from gwsproto.property_format import (
    SpaceheatName,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class AdsChannelConfig(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/ads.channel.config/000"""

    ChannelName: SpaceheatName
    TerminalBlockIdx: PositiveInt
    ThermistorDeviceType: str
    DataProcessingMethod: Optional[ThermistorDataMethod] = None
    DataProcessingDescription: Optional[str] = None
    TypeName: Literal["ads.channel.config"] = "ads.channel.config"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow", use_enum_values=True)
