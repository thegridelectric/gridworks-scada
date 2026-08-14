from typing import Literal

from pydantic import BaseModel, PositiveInt

from gwsproto.property_format import SpaceheatName


class I2cThermistorChannelConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.channel.config/000"""

    ChannelName: SpaceheatName
    AdcChannel: Literal["P0", "P1", "P2", "P3"]
    ThermistorBeta: PositiveInt

    TypeName: Literal["i2c.thermistor.channel.config"] = "i2c.thermistor.channel.config"
    Version: Literal["000"] = "000"
