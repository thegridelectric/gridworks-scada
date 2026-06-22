from typing import Literal

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.named_types.i2c_bit_address import I2cBitAddress
from gwsproto.property_format import NonNegativeInt, SpaceheatName, UUID4Str


class I2cWriteBit(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.write.bit/000"""

    Bus: SpaceheatName
    Address: I2cBitAddress
    Value: NonNegativeInt
    TriggerId: UUID4Str
    TypeName: Literal["i2c.write.bit"] = "i2c.write.bit"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: BitValueRange. Value SHALL be 0 or 1."""
        if self.Value not in (0, 1):
            raise ValueError(
                f"Axiom 1 (BitValueRange) failed: Value {self.Value} must be 0 or 1."
            )
        return self
