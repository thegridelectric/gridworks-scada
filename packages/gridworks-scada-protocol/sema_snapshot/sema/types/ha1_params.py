from typing import Literal, Self
from pydantic import StrictFloat, StrictInt, model_validator
from sema_snapshot.sema.base import SemaType


class Ha1Params(SemaType):
    """Sema: https://schemas.electricity.works/types/ha1.params/007"""

    alpha_times10: StrictInt
    beta_times100: StrictInt
    gamma_ex6: StrictInt
    intermediate_power_kw: StrictFloat
    intermediate_rswt_f: StrictInt
    dd_power_kw: StrictFloat
    dd_rswt_f: StrictInt
    dd_delta_t_f: StrictInt
    hp_max_kw_el: StrictFloat
    max_ewt_f: StrictInt
    load_overestimation_percent: StrictInt
    cop_intercept: StrictFloat
    cop_lwt_minus_oat_coeff: StrictFloat
    hp_turn_on_minutes: StrictInt
    type_name: Literal["ha1.params"] = "ha1.params"
    version: Literal["007"] = "007"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: NonPositiveCopLiftCoefficient
        CopLwtMinusOatCoeff SHALL be at most zero.
        """
        if self.cop_lwt_minus_oat_coeff > 0:
            raise ValueError(
                "Axiom 1 (NonPositiveCopLiftCoefficient) failed: "
                f"CopLwtMinusOatCoeff must be at most zero, got "
                f"{self.cop_lwt_minus_oat_coeff}."
            )
        return self
