from typing import Literal, Self
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonNegativeInt


class FloTuningBruce(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.tuning.bruce/000"""

    storage_losses_percent: StrictFloat
    hp_min_kw_el: StrictFloat
    hp_max_kw_th: StrictFloat
    max_load_kw_th: StrictFloat
    hp_constant_lift_f: StrictFloat
    load_bucket_upper_kwh_list: list[StrictFloat]
    rwt_intercept_by_bucket_list: list[StrictFloat]
    rwt_slope_by_bucket_list: list[StrictFloat]
    rwt_min_f: StrictFloat
    rswt_penalty_enabled: bool
    rswt_penalty_weight: StrictFloat
    rswt_penalty_decay: StrictFloat
    rswt_penalty_exponent_rate: StrictFloat
    rswt_penalty_decay_max_hour: NonNegativeInt
    short_cycle_penalty_enabled: bool
    short_cycle_penalty_weight: StrictFloat
    stability_penalty_enabled: bool
    stability_penalty_weight: StrictFloat
    stability_penalty_decay: StrictFloat
    stability_penalty_threshold_kwh: StrictFloat
    stability_penalty_threshold_price_mwh: StrictFloat
    stability_penalty_horizon_hours: NonNegativeInt
    terminal_cost_enabled: bool
    terminal_cost_end_window_hours: NonNegativeInt
    type_name: Literal["flo.tuning.bruce"] = "flo.tuning.bruce"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: OneLinePerBucket
        RwtInterceptByBucketList and RwtSlopeByBucketList SHALL each have
        exactly one more element than LoadBucketUpperKwhList.
        """
        n = len(self.load_bucket_upper_kwh_list) + 1
        if (
            len(self.rwt_intercept_by_bucket_list) != n
            or len(self.rwt_slope_by_bucket_list) != n
        ):
            raise ValueError(
                "Axiom 1 (OneLinePerBucket) failed: RwtInterceptByBucketList "
                f"({len(self.rwt_intercept_by_bucket_list)}) and RwtSlopeByBucketList "
                f"({len(self.rwt_slope_by_bucket_list)}) must each have {n} elements, "
                "one more than LoadBucketUpperKwhList."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: BucketsAscend
        LoadBucketUpperKwhList SHALL be positive and strictly increasing.
        """
        bounds = self.load_bucket_upper_kwh_list
        if any(b <= 0 for b in bounds) or any(
            b <= a for a, b in zip(bounds, bounds[1:])
        ):
            raise ValueError(
                "Axiom 2 (BucketsAscend) failed: LoadBucketUpperKwhList must be "
                f"positive and strictly increasing; got {bounds!r}."
            )
        return self
