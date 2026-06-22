from typing import Literal

from pydantic import BaseModel

from gwsproto.property_format import NonNegativeInt


class I2cBitAddress(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.bit.address/000"""

    I2cAddress: NonNegativeInt
    RegisterIndex: NonNegativeInt
    BitIndex: NonNegativeInt
    TypeName: Literal["i2c.bit.address"] = "i2c.bit.address"
    Version: Literal["000"] = "000"
