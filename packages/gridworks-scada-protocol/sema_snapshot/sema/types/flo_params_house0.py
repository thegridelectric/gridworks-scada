from typing import Literal
from pydantic import ConfigDict, StrictFloat, StrictInt
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import MarketPriceUnit
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UTCSeconds
from sema_snapshot.sema.property_format import UUID4Str


class FloParamsHouse0(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.params.house0/007"""

    g_node_alias: LeftRightDot
    flo_params_uid: UUID4Str
    timezone_str: str
    start_unix_s: UTCSeconds
    num_layers: PositiveInt
    horizon_hours: PositiveInt
    storage_volume_gallons: PositiveInt
    storage_losses_percent: StrictFloat
    hp_min_elec_kw: StrictFloat
    hp_max_elec_kw: StrictFloat
    max_hp_kwh_th: StrictFloat
    max_load_kwh_th: StrictFloat
    buffer_available_kwh: StrictFloat
    house_available_kwh: StrictFloat
    cop_intercept: StrictFloat
    cop_oat_coeff: StrictFloat
    cop_min: StrictFloat
    cop_min_oat_f: StrictFloat
    cop_lwt_coeff: StrictFloat
    initial_top_temp_f: StrictInt
    initial_middle_temp_f: StrictInt
    initial_bottom_temp_f: StrictInt
    hp_is_off: bool
    hp_turn_on_minutes: StrictInt
    lmp_forecast: list[StrictFloat] | None = None
    initial_thermocline1: StrictInt
    initial_thermocline2: StrictInt
    dist_price_forecast: list[StrictFloat] | None = None
    reg_price_forecast: list[StrictFloat] | None = None
    price_forecast_uid: UUID4Str
    oat_forecast_f: list[StrictFloat] | None = None
    wind_speed_forecast_mph: list[StrictFloat] | None = None
    weather_uid: UUID4Str
    alpha_times10: StrictInt
    beta_times100: StrictInt
    gamma_ex6: StrictInt
    intermediate_power_kw: StrictFloat
    intermediate_rswt_f: StrictInt
    dd_power_kw: StrictFloat
    dd_rswt_f: StrictInt
    dd_delta_t_f: StrictInt
    max_ewt_f: StrictInt
    rswt_penalty_enabled: bool
    stability_penalty_enabled: bool
    rswt_penalty_weight: StrictFloat
    rswt_penalty_decay: StrictFloat
    rswt_penalty_exponent_rate: StrictFloat
    rswt_penalty_decay_max_hour: StrictInt
    previous_plan_hp_kwh_el_list: list[StrictFloat] | None = None
    previous_estimate_storage_kwh_now: StrictFloat | None = None
    stability_penalty_weight: StrictFloat
    stability_penalty_decay: StrictFloat
    stability_penalty_threshold_kwh: StrictFloat
    stability_penalty_horizon_hours: StrictInt
    price_unit: MarketPriceUnit
    params_generated_s: UTCSeconds
    constant_delta_t: StrictInt
    flo_git_commit: str
    type_name: Literal["flo.params.house0"] = "flo.params.house0"
    version: Literal["007"] = "007"

    model_config = ConfigDict(**(SemaType.model_config | {"extra": "allow"}))
