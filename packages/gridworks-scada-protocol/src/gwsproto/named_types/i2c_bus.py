from typing import Literal

from gwsproto.property_format import NonNegativeInt, PascalCase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cBus(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.bus/000"""

    Name: PascalCase
    BusNumber: NonNegativeInt
    TypeName: Literal["i2c.bus"] = "i2c.bus"
    Version: Literal["000"] = "000"
