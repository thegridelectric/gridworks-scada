from typing import Literal

from gwsproto.property_format import NonNegativeInt
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cRegAddress(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.reg.address/000"""

    I2cAddress: NonNegativeInt
    RegisterIndex: NonNegativeInt
    TypeName: Literal["i2c.reg.address"] = "i2c.reg.address"
    Version: Literal["000"] = "000"
