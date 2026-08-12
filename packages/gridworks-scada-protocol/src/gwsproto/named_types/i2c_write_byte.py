from typing import Literal

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.property_format import NonNegativeInt, SpaceheatName, UUID4Str


class I2cWriteByte(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.write.byte/000"""

    Bus: SpaceheatName
    I2cAddress: NonNegativeInt
    Value: NonNegativeInt
    TriggerId: UUID4Str
    TypeName: Literal["i2c.write.byte"] = "i2c.write.byte"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: ByteValueRange. Value SHALL be less than 256."""
        if self.Value >= 256:
            raise ValueError(
                f"Axiom 1 (ByteValueRange) failed: Value {self.Value} is not less than 256."
            )
        return self
