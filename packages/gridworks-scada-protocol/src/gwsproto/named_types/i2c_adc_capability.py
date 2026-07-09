from typing import Literal

from pydantic import BaseModel, PositiveInt

from gwsproto.enums import I2cAdcType
from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cAdcCapability(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.adc.capability/000"""

    Name: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    AdcType: I2cAdcType
    Channels: PositiveInt
    TypeName: Literal["i2c.adc.capability"] = "i2c.adc.capability"
    Version: Literal["000"] = "000"
