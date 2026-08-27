import time
from typing import Literal, Self

from pydantic import BaseModel, StrictInt, model_validator

from gwsproto.property_format import UUID4Str, SpaceheatName


class I2cWriteBit(BaseModel):
    """ASL: https://schemas.electricity.works/types/i2c.write.bit/000"""

    Bus: SpaceheatName
    I2cAddress: StrictInt
    Register: StrictInt  
    BitIndex: StrictInt
    Value: Literal[0, 1]
    TriggerId: UUID4Str 

    TypeName: Literal["i2c.write.bit"] = "i2c.write.bit"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: I2C address validity.
        I2CAddress must be a valid 7-bit I2C address (0–127).
        """
        if not (0 <= self.I2cAddress <= 0x7F):
            raise ValueError(
                f"I2cAddress {self.I2cAddress} out of range (expected 0–127)"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: Register range.
        Register must fit in a single byte (0–255).
        """
        if not (0 <= self.Register <= 0xFF):
            raise ValueError(
                f"Register {self.Register} out of range (expected 0–255)"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: Bit index validity.
        BitIndex must be between 0 and 7 inclusive.
        """
        if not (0 <= self.BitIndex <= 7):
            raise ValueError(
                f"BitIndex {self.BitIndex} out of range (expected 0–7)"
            )
        return self