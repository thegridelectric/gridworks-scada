from typing import Literal

from pydantic import PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.named_types.i2c_reg_address import I2cRegAddress
from gwsproto.property_format import NonNegativeInt, SpaceheatName, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cWriteReg(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.write.reg/000"""

    Bus: SpaceheatName
    Address: I2cRegAddress
    NumBytes: PositiveInt
    Value: NonNegativeInt
    TriggerId: UUID4Str
    TypeName: Literal["i2c.write.reg"] = "i2c.write.reg"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: NumBytesRange. NumBytes SHALL be 1 or 2."""
        if self.NumBytes not in (1, 2):
            raise ValueError(
                f"Axiom 1 (NumBytesRange) failed: NumBytes {self.NumBytes} must be 1 or 2."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: ValueFitsNumBytes. Value SHALL fit in NumBytes bytes."""
        if not (0 <= self.Value <= 256**self.NumBytes - 1):
            raise ValueError(
                f"Axiom 2 (ValueFitsNumBytes) failed: Value {self.Value} does not fit "
                f"in NumBytes {self.NumBytes} byte(s)."
            )
        return self
