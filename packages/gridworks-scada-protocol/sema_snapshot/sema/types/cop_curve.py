from typing import Literal, Self
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType


class CopCurve(SemaType):
    """Sema: https://schemas.electricity.works/types/cop.curve/001"""

    intercept: StrictFloat
    lwt_minus_oat_coeff: StrictFloat
    type_name: Literal["cop.curve"] = "cop.curve"
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: NonPositiveLiftCoefficient
        LwtMinusOatCoeff SHALL be at most zero.
        """
        if self.lwt_minus_oat_coeff > 0:
            raise ValueError(
                "Axiom 1 (NonPositiveLiftCoefficient) failed: LwtMinusOatCoeff "
                f"must be at most zero, got {self.lwt_minus_oat_coeff}."
            )
        return self
