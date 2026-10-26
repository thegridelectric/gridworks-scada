from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str


class I2cWriteByte(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.write.byte/000"""

    bus: SpaceheatName
    i2c_address: NonNegativeInt
    value: NonNegativeInt
    trigger_id: UUID4Str
    type_name: Literal["i2c.write.byte"] = "i2c.write.byte"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cWriteByte":
        """
        Axiom 1: ByteValueRange
        Value SHALL be less than 256.
        """
        if self.value >= 256:
            raise ValueError(
                f"Axiom 1 (ByteValueRange) failed: Value {self.value} is not less than 256."
            )
        return self
