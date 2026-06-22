from typing import Literal

from pydantic import BaseModel, PositiveInt

from gwsproto.enums import I2cDacType
from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cDacConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.dac.config/000"""

    DacName: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    DacType: I2cDacType
    Channels: PositiveInt
    TypeName: Literal["i2c.dac.config"] = "i2c.dac.config"
    Version: Literal["000"] = "000"
