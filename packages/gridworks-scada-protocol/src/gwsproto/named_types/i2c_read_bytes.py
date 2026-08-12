from typing import Literal

from pydantic import BaseModel, PositiveInt

from gwsproto.property_format import NonNegativeInt, SpaceheatName, UUID4Str


class I2cReadBytes(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.read.bytes/000"""

    Bus: SpaceheatName
    I2cAddress: NonNegativeInt
    NumBytes: PositiveInt
    TriggerId: UUID4Str
    TypeName: Literal["i2c.read.bytes"] = "i2c.read.bytes"
    Version: Literal["000"] = "000"
