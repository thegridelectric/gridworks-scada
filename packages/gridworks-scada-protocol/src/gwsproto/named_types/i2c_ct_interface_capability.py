from typing import Literal

from pydantic import PositiveFloat, PositiveInt

from gwsproto.enums import I2cAdcType
from gwsproto.property_format import NonNegativeInt, PascalCase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cCtInterfaceCapability(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.ct.interface.capability/000"""

    Name: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    AdcType: I2cAdcType
    AdcReferenceVolts: PositiveFloat
    Channels: PositiveInt
    TypeName: Literal["i2c.ct.interface.capability"] = "i2c.ct.interface.capability"
    Version: Literal["000"] = "000"
