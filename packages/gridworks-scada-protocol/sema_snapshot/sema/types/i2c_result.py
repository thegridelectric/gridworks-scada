from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import I2cOperation
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str


class I2cResult(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.result/001"""

    bus: SpaceheatName
    operation: I2cOperation
    value: NonNegativeInt | None = None
    bytes: list[NonNegativeInt] | None = None
    success: bool
    error: str | None = None
    unix_time_ms: UTCMilliseconds
    trigger_id: UUID4Str
    type_name: Literal["i2c.result"] = "i2c.result"
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cResult":
        """
        Axiom 1: ErrorIffFailure
        Error SHALL be present and non-blank if and only if Success is false.
        """
        has_error = self.error is not None and self.error.strip() != ""
        if self.success and has_error:
            raise ValueError(
                "Axiom 1 (ErrorIffFailure) failed: Success is true but Error is present."
            )
        if not self.success and not has_error:
            raise ValueError(
                "Axiom 1 (ErrorIffFailure) failed: Success is false but Error is missing or blank."
            )
        return self
