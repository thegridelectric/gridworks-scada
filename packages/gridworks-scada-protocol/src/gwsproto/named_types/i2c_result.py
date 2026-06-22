from typing import Literal

from pydantic import BaseModel, model_validator
from typing_extensions import Self

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

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: ErrorIffFailure. Error SHALL be present and non-blank if and only
        if Success is false."""
        has_error = self.Error is not None and self.Error.strip() != ""
        if self.Success and has_error:
            raise ValueError(
                "Axiom 1 (ErrorIffFailure) failed: Success is true but Error is present."
            )
        if not self.Success and not has_error:
            raise ValueError(
                "Axiom 1 (ErrorIffFailure) failed: Success is false but Error is missing or blank."
            )
        return self
