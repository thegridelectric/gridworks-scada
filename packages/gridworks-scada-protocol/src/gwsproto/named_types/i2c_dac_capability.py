from typing import Literal

from pydantic import BaseModel, PositiveInt

from gwsproto.enums import I2cDacType
from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cDacCapability(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.dac.capability/000"""

    DacName: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    DacType: I2cDacType
    Channels: PositiveInt
    TypeName: Literal["i2c.dac.capability"] = "i2c.dac.capability"
    Version: Literal["000"] = "000"
