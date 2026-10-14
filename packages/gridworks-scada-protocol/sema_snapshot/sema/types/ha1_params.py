from typing import Literal
from pydantic import StrictFloat, StrictInt
from sema_snapshot.sema.base import SemaType


class Ha1Params(SemaType):
    """Sema: https://schemas.electricity.works/types/ha1.params/006"""

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
    cop_oat_coeff: StrictFloat
    cop_lwt_coeff: StrictFloat
    cop_min: StrictFloat
    cop_min_oat_f: StrictFloat
    hp_turn_on_minutes: StrictInt
    type_name: Literal["ha1.params"] = "ha1.params"
    version: Literal["006"] = "006"
