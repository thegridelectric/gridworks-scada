from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonNegativeInt


class I2cBitAddress(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.bit.address/000"""

    i2c_address: NonNegativeInt
    register_index: NonNegativeInt
    bit_index: NonNegativeInt
    type_name: Literal["i2c.bit.address"] = "i2c.bit.address"
    version: Literal["000"] = "000"
