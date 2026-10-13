from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.i2c_bit_address import I2cBitAddress


class I2cWriteBit(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.write.bit/000"""

    bus: SpaceheatName
    address: I2cBitAddress
    value: NonNegativeInt
    trigger_id: UUID4Str
    type_name: Literal["i2c.write.bit"] = "i2c.write.bit"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cWriteBit":
        """
        Axiom 1: BitValueRange
        Value SHALL be 0 or 1.
        """
        if self.value not in (0, 1):
            raise ValueError(
                f"Axiom 1 (BitValueRange) failed: Value {self.value} must be 0 or 1."
            )
        return self
