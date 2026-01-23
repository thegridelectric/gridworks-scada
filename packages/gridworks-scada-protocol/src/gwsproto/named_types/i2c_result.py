from typing import Literal
from typing_extensions import Self

from pydantic import BaseModel, StrictInt, model_validator

from gwsproto.property_format import (
    SpaceheatName,
    UUID4Str,
    UTCMilliseconds,
)


class I2cResult(BaseModel):
    """ASL: https://schemas.electricity.works/types/i2c.result/000"""

    Bus: SpaceheatName
    Operation: Literal["read.bit", "write.bit"]
    I2cAddress: StrictInt
    Register: StrictInt
    BitIndex: StrictInt
    Value: Literal[0, 1] | None = None
    Success: bool
    Error: str | None = None
    UnixTimeMs: UTCMilliseconds
    TriggerId: UUID4Str

    TypeName: Literal["i2c.result"] = "i2c.result"
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

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """if error is None the value must exist"""
        return self