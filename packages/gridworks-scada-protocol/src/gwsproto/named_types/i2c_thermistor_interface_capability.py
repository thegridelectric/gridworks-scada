from typing import Literal

from pydantic import BaseModel, PositiveFloat, PositiveInt

from gwsproto.enums import I2cAdcType
from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cThermistorInterfaceCapability(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.interface.capability/000"""

    Name: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    AdcType: I2cAdcType
    SupportedDataRatesSps: list[PositiveInt]
    AdcReferenceVolts: PositiveFloat
    SeriesResistanceKOhms: PositiveFloat
    TypeName: Literal["i2c.thermistor.interface.capability"] = "i2c.thermistor.interface.capability"
    Version: Literal["000"] = "000"
