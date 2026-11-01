from typing import List, Literal

from pydantic import NonNegativeInt, model_validator
from typing_extensions import Self

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloTuningBruce(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.tuning.bruce/000"""

    StorageLossesPercent: float
    HpMinKwEl: float
    HpMaxKwTh: float
    MaxLoadKwTh: float
    HpConstantLiftF: float
    LoadBucketUpperKwhList: List[float]
    RwtInterceptByBucketList: List[float]
    RwtSlopeByBucketList: List[float]
    RwtMinF: float
    RswtPenaltyEnabled: bool
    RswtPenaltyWeight: float
    RswtPenaltyDecay: float
    RswtPenaltyExponentRate: float
    RswtPenaltyDecayMaxHour: NonNegativeInt
    ShortCyclePenaltyEnabled: bool
    ShortCyclePenaltyWeight: float
    StabilityPenaltyEnabled: bool
    StabilityPenaltyWeight: float
    StabilityPenaltyDecay: float
    StabilityPenaltyThresholdKwh: float
    StabilityPenaltyThresholdPriceMwh: float
    StabilityPenaltyHorizonHours: NonNegativeInt
    TerminalCostEnabled: bool
    TerminalCostEndWindowHours: NonNegativeInt
    TypeName: Literal["flo.tuning.bruce"] = "flo.tuning.bruce"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: OneLinePerBucket.
        RwtInterceptByBucketList and RwtSlopeByBucketList SHALL each have
        exactly one more element than LoadBucketUpperKwhList.
        """
        n = len(self.LoadBucketUpperKwhList) + 1
        if len(self.RwtInterceptByBucketList) != n or len(self.RwtSlopeByBucketList) != n:
            raise ValueError(
                "Axiom 1 (OneLinePerBucket) failed: RwtInterceptByBucketList "
                f"({len(self.RwtInterceptByBucketList)}) and RwtSlopeByBucketList "
                f"({len(self.RwtSlopeByBucketList)}) must each have {n} elements, "
                "one more than LoadBucketUpperKwhList"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: BucketsAscend.
        LoadBucketUpperKwhList SHALL be positive and strictly increasing.
        """
        bounds = self.LoadBucketUpperKwhList
        if any(b <= 0 for b in bounds) or any(b <= a for a, b in zip(bounds, bounds[1:])):
            raise ValueError(
                "Axiom 2 (BucketsAscend) failed: LoadBucketUpperKwhList must be "
                f"positive and strictly increasing; got {bounds}"
            )
        return self
