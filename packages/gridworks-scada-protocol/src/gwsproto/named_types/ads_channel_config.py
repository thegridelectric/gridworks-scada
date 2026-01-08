from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt

from gwsproto.enums import MakeModel, ThermistorDataMethod
from gwsproto.named_types.channel_config import ChannelConfig
from gwsproto.property_format import (
    SpaceheatName,
)


class AdsChannelConfig(ChannelConfig):
    ChannelName: SpaceheatName
    TerminalBlockIdx: PositiveInt
    ThermistorMakeModel: MakeModel
    DataProcessingMethod: Optional[ThermistorDataMethod] = None
    DataProcessingDescription: Optional[str] = None
    TypeName: Literal["ads.channel.config"] = "ads.channel.config"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow", use_enum_values=True)
