from typing import Literal

from pydantic import PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.named_types.i2c_reg_address import I2cRegAddress
from gwsproto.property_format import SpaceheatName, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cReadReg(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.read.reg/000"""

    Bus: SpaceheatName
    Address: I2cRegAddress
    NumBytes: PositiveInt
    TriggerId: UUID4Str
    TypeName: Literal["i2c.read.reg"] = "i2c.read.reg"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: NumBytesRange. NumBytes SHALL be 1 or 2."""
        if self.NumBytes not in (1, 2):
            raise ValueError(
                f"Axiom 1 (NumBytesRange) failed: NumBytes {self.NumBytes} must be 1 or 2."
            )
        return self
