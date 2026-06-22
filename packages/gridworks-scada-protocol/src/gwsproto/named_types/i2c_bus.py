from typing import Literal

from pydantic import BaseModel

from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cBus(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.bus/000"""

    Name: PascalCase
    BusNumber: NonNegativeInt
    TypeName: Literal["i2c.bus"] = "i2c.bus"
    Version: Literal["000"] = "000"
