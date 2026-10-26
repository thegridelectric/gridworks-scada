from typing import Literal

from pydantic import PositiveInt

from gwsproto.property_format import NonNegativeInt, SpaceheatName, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cReadBytes(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.read.bytes/000"""

    Bus: SpaceheatName
    I2cAddress: NonNegativeInt
    NumBytes: PositiveInt
    TriggerId: UUID4Str
    TypeName: Literal["i2c.read.bytes"] = "i2c.read.bytes"
    Version: Literal["000"] = "000"
