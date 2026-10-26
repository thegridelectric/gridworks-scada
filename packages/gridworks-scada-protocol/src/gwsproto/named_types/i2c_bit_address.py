from typing import Literal

from gwsproto.property_format import NonNegativeInt
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cBitAddress(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.bit.address/000"""

    I2cAddress: NonNegativeInt
    RegisterIndex: NonNegativeInt
    BitIndex: NonNegativeInt
    TypeName: Literal["i2c.bit.address"] = "i2c.bit.address"
    Version: Literal["000"] = "000"
