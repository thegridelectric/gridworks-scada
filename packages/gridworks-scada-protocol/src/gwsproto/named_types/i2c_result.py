from typing import Literal

from pydantic import BaseModel

from gwsproto.enums.i2c_operation import I2cOperation
from gwsproto.property_format import (
    NonNegativeInt,
    SpaceheatName,
    UTCMilliseconds,
    UUID4Str,
)


class I2cResult(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.result/000"""

    Bus: SpaceheatName
    Operation: I2cOperation
    Value: NonNegativeInt | None = None
    Success: bool
    Error: str | None = None
    UnixTimeMs: UTCMilliseconds
    TriggerId: UUID4Str
    TypeName: Literal["i2c.result"] = "i2c.result"
    Version: Literal["000"] = "000"
