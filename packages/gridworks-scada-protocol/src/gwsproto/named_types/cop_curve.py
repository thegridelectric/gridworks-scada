from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class CopCurve(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/cop.curve/001"""

    Intercept: float
    LwtMinusOatCoeff: float
    TypeName: Literal["cop.curve"] = "cop.curve"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: NonPositiveLiftCoefficient.
        LwtMinusOatCoeff SHALL be at most zero.
        """
        if self.LwtMinusOatCoeff > 0:
            raise ValueError(
                "Axiom 1 (NonPositiveLiftCoefficient) failed: LwtMinusOatCoeff "
                f"must be at most zero, got {self.LwtMinusOatCoeff}."
            )
        return self
