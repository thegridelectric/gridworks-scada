
from typing import Literal
from pydantic import PositiveInt
from gwsproto.named_types.channel_config import ChannelConfig


class I2cThermistorChannelConfig(ChannelConfig):
    AdcChannel: Literal["P0", "P1", "P2", "P3"]
    SendToDerived: bool = False
    ThermistorBeta: PositiveInt

    TypeName: Literal["i2c.thermistor.channel.config"] = "i2c.thermistor.channel.config"
    Version: Literal["000"] = "000"