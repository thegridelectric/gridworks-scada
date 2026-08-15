from typing import Literal

from pydantic import PositiveInt

from gwsproto.enums import I2cMuxType
from gwsproto.property_format import NonNegativeInt, PascalCase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cMux(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.mux/000"""

    MuxName: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    MuxType: I2cMuxType
    Channels: PositiveInt
    TypeName: Literal["i2c.mux"] = "i2c.mux"
    Version: Literal["000"] = "000"
