from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonNegativeInt


class I2cRegAddress(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.reg.address/000"""

    i2c_address: NonNegativeInt
    register_index: NonNegativeInt
    type_name: Literal["i2c.reg.address"] = "i2c.reg.address"
    version: Literal["000"] = "000"
