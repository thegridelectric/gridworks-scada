from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveFloat
from sema_snapshot.sema.property_format import PositiveInt


class HeatingCurve(SemaType):
    """Sema: https://schemas.electricity.works/types/heating.curve/001"""

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
    rho_times100: StrictInt
    intermediate_power_kw: PositiveFloat
    intermediate_rswt_f: PositiveInt
    dd_power_kw: PositiveFloat
    dd_rswt_f: PositiveInt
    dd_room_temp_f: PositiveInt
    dd_delta_t_f: PositiveInt
    max_ewt_f: PositiveInt
    mass_flow_kg_h: PositiveInt
    type_name: Literal["heating.curve"] = "heating.curve"
    version: Literal["001"] = "001"
