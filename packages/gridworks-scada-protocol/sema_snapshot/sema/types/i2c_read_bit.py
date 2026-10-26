from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.i2c_bit_address import I2cBitAddress


class I2cReadBit(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.read.bit/000"""

    bus: SpaceheatName
    address: I2cBitAddress
    trigger_id: UUID4Str
    type_name: Literal["i2c.read.bit"] = "i2c.read.bit"
    version: Literal["000"] = "000"
