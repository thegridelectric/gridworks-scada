
from typing import Literal
from pydantic import PositiveInt, model_validator
from typing_extensions import Self
from gwsproto.type_helpers.channel_config_base import (
    ChannelConfigBase,
    check_async_capture_consistency,
    check_channel_config_axiom_1,
)


class I2cThermistorChannelConfig(ChannelConfigBase):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.channel.config/002"""

    AdcChannel: Literal["P0", "P1", "P2", "P3"]
    SendToDerived: bool = False
    ThermistorBeta: PositiveInt

    TypeName: Literal["i2c.thermistor.channel.config"] = "i2c.thermistor.channel.config"
    Version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: AsyncCaptureConsistency.
        If AsyncCapture is true, AsyncCaptureDelta must be present.
        """
        return check_async_capture_consistency(self)

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: CapturePollingConsistency.
        If PollPeriodMs exists, then CapturePeriodMs (CapturePeriodS * 1000)
        must be larger than PollPeriodMs. If CapturePeriodMs is less than
        10 * PollPeriodMs, then CapturePeriodMs must be a multiple of
        PollPeriodMs.
        """
        return check_channel_config_axiom_1(self, axiom_number=2)
