from typing import Literal

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class Ha1Params(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/ha1.params/007
    """

    AlphaTimes10: StrictInt
    BetaTimes100: StrictInt
    GammaEx6: StrictInt
    IntermediatePowerKw: float
    IntermediateRswtF: StrictInt
    DdPowerKw: float
    DdRswtF: StrictInt
    DdDeltaTF: StrictInt
    HpMaxKwEl: float
    MaxEwtF: StrictInt
    LoadOverestimationPercent: StrictInt
    CopIntercept: float
    CopLwtMinusOatCoeff: float
    HpTurnOnMinutes: StrictInt
    TypeName: Literal["ha1.params"] = "ha1.params"
    Version: Literal["007"] = "007"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: NonPositiveCopLiftCoefficient.
        CopLwtMinusOatCoeff SHALL be at most zero.
        """
        if self.CopLwtMinusOatCoeff > 0:
            raise ValueError(
                "Axiom 1 (NonPositiveCopLiftCoefficient) failed: "
                f"CopLwtMinusOatCoeff must be at most zero, got {self.CopLwtMinusOatCoeff}."
            )
        return self
