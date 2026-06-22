from typing import Literal

from pydantic import BaseModel

from gwsproto.named_types.i2c_reg_address import I2cRegAddress
from gwsproto.property_format import NonNegativeInt, SpaceheatName, UUID4Str


class I2cWriteReg(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.write.reg/000"""

    Bus: SpaceheatName
    Address: I2cRegAddress
    NumBytes: Literal[1, 2]
    Value: NonNegativeInt
    TriggerId: UUID4Str
    TypeName: Literal["i2c.write.reg"] = "i2c.write.reg"
    Version: Literal["000"] = "000"
