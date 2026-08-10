from typing import Literal

from pydantic import BaseModel, PositiveInt

from gwsproto.enums import I2cMuxType
from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cMux(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.mux/000"""

    MuxName: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    MuxType: I2cMuxType
    Channels: PositiveInt
    TypeName: Literal["i2c.mux"] = "i2c.mux"
    Version: Literal["000"] = "000"
