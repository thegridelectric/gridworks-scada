from typing import Literal

from pydantic import BaseModel, PositiveFloat

from gwsproto.enums import I2cAdcType
from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cThermistorInterfaceConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.interface.config/000"""

    Name: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    AdcType: I2cAdcType
    AdcReferenceVolts: PositiveFloat
    SeriesResistanceKOhms: PositiveFloat
    TypeName: Literal["i2c.thermistor.interface.config"] = "i2c.thermistor.interface.config"
    Version: Literal["000"] = "000"
