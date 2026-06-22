from typing import Literal

from pydantic import BaseModel

from gwsproto.property_format import NonNegativeInt


class I2cRegAddress(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.reg.address/000"""

    I2cAddress: NonNegativeInt
    RegisterIndex: NonNegativeInt
    TypeName: Literal["i2c.reg.address"] = "i2c.reg.address"
    Version: Literal["000"] = "000"
