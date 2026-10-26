from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import I2cAdcChannel
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName


class I2cThermistorChannelConfig(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.channel.config/000"""

    channel_name: SpaceheatName
    adc_channel: I2cAdcChannel
    thermistor_beta: PositiveInt
    type_name: Literal["i2c.thermistor.channel.config"] = (
        "i2c.thermistor.channel.config"
    )
    version: Literal["000"] = "000"
