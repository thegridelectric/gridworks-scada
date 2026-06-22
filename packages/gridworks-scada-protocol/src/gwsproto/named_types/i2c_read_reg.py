from typing import Literal

from pydantic import BaseModel

from gwsproto.named_types.i2c_reg_address import I2cRegAddress
from gwsproto.property_format import SpaceheatName, UUID4Str


class I2cReadReg(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.read.reg/000"""

    Bus: SpaceheatName
    Address: I2cRegAddress
    NumBytes: Literal[1, 2]
    TriggerId: UUID4Str
    TypeName: Literal["i2c.read.reg"] = "i2c.read.reg"
    Version: Literal["000"] = "000"
