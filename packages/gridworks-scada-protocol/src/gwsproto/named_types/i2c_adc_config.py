from typing import Literal

from pydantic import BaseModel, PositiveInt

from gwsproto.enums import I2cAdcType
from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cAdcConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.adc.config/000"""

    Name: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    AdcType: I2cAdcType
    Channels: PositiveInt
    TypeName: Literal["i2c.adc.config"] = "i2c.adc.config"
    Version: Literal["000"] = "000"
