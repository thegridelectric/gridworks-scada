from typing import Literal

from gwsproto.named_types.channel_config import ChannelConfig
from gwsproto.named_types.egauge_register_config import (
    EgaugeRegisterConfig as EgaugeConfig,
)


class ElectricMeterChannelConfig(ChannelConfig):
    EgaugeRegisterConfig: EgaugeConfig | None = None
    TypeName: Literal["electric.meter.channel.config"] = "electric.meter.channel.config"
    Version: Literal["000"] = "000"
