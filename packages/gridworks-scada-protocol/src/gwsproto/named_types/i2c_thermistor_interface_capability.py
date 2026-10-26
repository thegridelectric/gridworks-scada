from typing import Literal

from pydantic import PositiveFloat, PositiveInt

from gwsproto.enums import I2cAdcType
from gwsproto.property_format import NonNegativeInt, PascalCase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cThermistorInterfaceCapability(GwsprotoSemaType):
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
