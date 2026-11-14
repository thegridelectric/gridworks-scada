from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveFloat
from sema_snapshot.sema.property_format import PositiveInt


class HeatingCurve(SemaType):
    """Sema: https://schemas.electricity.works/types/heating.curve/000"""

    baseline_alpha_times10: StrictInt
    baseline_beta_times100: StrictInt
    baseline_gamma_ex6: StrictInt
    alpha_ex6: StrictInt
    beta_ex6: StrictInt
    gamma_ex6: StrictInt
    delta_ex6: StrictInt
    epsilon_ex6: StrictInt
    zeta_ex6: StrictInt
    eta_ex6: StrictInt
    rho_times100: PositiveInt
    intermediate_power_kw: PositiveFloat
    intermediate_rswt_f: PositiveInt
    dd_power_kw: PositiveFloat
    dd_rswt_f: PositiveInt
    dd_room_temp_f: PositiveInt
    dd_delta_t_f: PositiveInt
    max_ewt_f: PositiveInt
    mass_flow_kg_h: PositiveInt
    type_name: Literal["heating.curve"] = "heating.curve"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "HeatingCurve":
        """
        Axiom 1: DesignDayRswtIsHottest
        DdRswtF SHALL be greater than or equal to IntermediateRswtF.
        """
        if self.dd_rswt_f < self.intermediate_rswt_f:
            raise ValueError(
                f"Axiom 1 (DesignDayRswtIsHottest) failed: DdRswtF {self.dd_rswt_f} "
                f"is below IntermediateRswtF {self.intermediate_rswt_f}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "HeatingCurve":
        """
        Axiom 2: DesignDayPowerIsLargest
        DdPowerKw SHALL be greater than or equal to IntermediatePowerKw.
        """
        if self.dd_power_kw < self.intermediate_power_kw:
            raise ValueError(
                f"Axiom 2 (DesignDayPowerIsLargest) failed: DdPowerKw {self.dd_power_kw} "
                f"is below IntermediatePowerKw {self.intermediate_power_kw}."
            )
        return self
