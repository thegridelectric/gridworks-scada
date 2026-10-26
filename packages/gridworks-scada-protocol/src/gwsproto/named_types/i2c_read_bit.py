from typing import Literal

from gwsproto.named_types.i2c_bit_address import I2cBitAddress
from gwsproto.property_format import SpaceheatName, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cReadBit(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.read.bit/000"""

    Bus: SpaceheatName
    Address: I2cBitAddress
    TriggerId: UUID4Str
    TypeName: Literal["i2c.read.bit"] = "i2c.read.bit"
    Version: Literal["000"] = "000"
