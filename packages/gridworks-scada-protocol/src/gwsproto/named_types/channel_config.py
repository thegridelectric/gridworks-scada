from pydantic import model_validator
from typing_extensions import Self

from gwsproto.type_helpers.channel_config_base import (
    ChannelConfigBase,
    check_channel_config_axiom_1,
)


class ChannelConfig(ChannelConfigBase):
    """Sema: https://schemas.electricity.works/types/channel.config/000"""

    TypeName: str = "channel.config"
    Version: str = "000"


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
