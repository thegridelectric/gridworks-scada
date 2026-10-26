from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.i2c_reg_address import I2cRegAddress


class I2cReadReg(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.read.reg/000"""

    bus: SpaceheatName
    address: I2cRegAddress
    num_bytes: PositiveInt
    trigger_id: UUID4Str
    type_name: Literal["i2c.read.reg"] = "i2c.read.reg"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cReadReg":
        """
        Axiom 1: NumBytesRange
        NumBytes SHALL be 1 or 2.
        """
        if self.num_bytes not in (1, 2):
            raise ValueError(
                f"Axiom 1 (NumBytesRange) failed: NumBytes {self.num_bytes} must be 1 or 2."
            )
        return self
