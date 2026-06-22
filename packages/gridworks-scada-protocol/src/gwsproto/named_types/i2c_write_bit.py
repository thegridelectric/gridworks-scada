from typing import Literal

from pydantic import BaseModel

from gwsproto.named_types.i2c_bit_address import I2cBitAddress
from gwsproto.property_format import SpaceheatName, UUID4Str


class I2cWriteBit(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.write.bit/000"""

    Bus: SpaceheatName
    Address: I2cBitAddress
    Value: Literal[0, 1]
    TriggerId: UUID4Str
    TypeName: Literal["i2c.write.bit"] = "i2c.write.bit"
    Version: Literal["000"] = "000"
