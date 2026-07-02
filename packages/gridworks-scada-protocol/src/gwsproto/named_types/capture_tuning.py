from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.type_helpers.channel_config_base import (
    ChannelConfigBase,
    check_channel_config_axiom_1,
)


class CaptureTuning(ChannelConfigBase):
    """Sema: https://schemas.electricity.works/types/capture.tuning/000"""

    TypeName: Literal["capture.tuning"] = "capture.tuning"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: CaptureAndPollingConsistency.
        If PollPeriodMs exists, then CapturePeriodMs (CapturePeriodS * 1000)
        must be larger than PollPeriodMs. If CapturePeriodMs is less than
        10 * PollPeriodMs, then CapturePeriodMs must be a multiple of
        PollPeriodMs.
        """
        return check_channel_config_axiom_1(self)
