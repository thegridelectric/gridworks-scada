from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import ThermistorDataMethod
from gwsproto.property_format import (
    SpaceheatName,
)
from gwsproto.type_helpers.channel_config_base import (
    ChannelConfigBase,
    check_channel_config_axiom_1,
)


class AdsChannelConfig(ChannelConfigBase):
    ChannelName: SpaceheatName
    TerminalBlockIdx: PositiveInt
    ThermistorDeviceType: str
    DataProcessingMethod: Optional[ThermistorDataMethod] = None
    DataProcessingDescription: Optional[str] = None
    TypeName: Literal["ads.channel.config"] = "ads.channel.config"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Capture and Polling Consistency.
        If PollPeriodMs exists, then CapturePeriodMs (CapturePeriodS * 1000)
        must be larger than PollPeriodMs. If CapturePeriodMs is less than
        10 * PollPeriodMs, then CapturePeriodMs must be a multiple of
        PollPeriodMs.
        """
        return check_channel_config_axiom_1(self)
