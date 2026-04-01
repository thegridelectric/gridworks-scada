from typing import Literal

from pydantic import PositiveInt, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.type_helpers.channel_config_base import (
    ChannelConfigBase,
    check_channel_config_axiom_1,
)


class DfrConfig(ChannelConfigBase):
    OutputIdx: PositiveInt
    InitialVoltsTimes100: StrictInt
    TypeName: Literal["dfr.config"] = "dfr.config"
    Version: Literal["000"] = "000"

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
