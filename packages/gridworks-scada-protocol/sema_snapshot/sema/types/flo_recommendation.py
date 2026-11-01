from typing import Literal, Self
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import MarketPriceUnit
from sema_snapshot.sema.enums import MarketQuantityUnit
from sema_snapshot.sema.property_format import GitCommit
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import NonEmptyString
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.types.flo_optimal_path import FloOptimalPath
from sema_snapshot.sema.types.price_quantity_unitless import PriceQuantityUnitless


class FloRecommendation(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.recommendation/000"""

    bidder_alias: LeftRightDot
    pq_pairs: list[PriceQuantityUnitless]
    price_unit: MarketPriceUnit
    quantity_unit: MarketQuantityUnit
    optimal_path_list: list[FloOptimalPath]
    flo_name: LeftRightDot
    flo_repo: NonEmptyString
    flo_git_commit: GitCommit
    created_ms: UTCMilliseconds
    type_name: Literal["flo.recommendation"] = "flo.recommendation"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: AtLeastOnePair
        PqPairs SHALL have at least one element.
        """
        if len(self.pq_pairs) == 0:
            raise ValueError(
                "Axiom 1 (AtLeastOnePair) failed: PqPairs must not be empty."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: PathPerPair
        OptimalPathList SHALL have the same length as PqPairs.
        """
        if len(self.optimal_path_list) != len(self.pq_pairs):
            raise ValueError(
                "Axiom 2 (PathPerPair) failed: OptimalPathList "
                f"({len(self.optimal_path_list)}) and PqPairs ({len(self.pq_pairs)}) "
                "must have the same length."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: FirstStepIsTheBid
        For every i, the first element of OptimalPathList[i].HpAvgWList
        SHALL equal PqPairs[i].QuantityX1000 expressed in watts: as is
        when QuantityUnit is AvgkW, times 1000 when it is AvgMW.
        """
        to_watts = 1000 if self.quantity_unit.value == "AvgMW" else 1
        for i, (pair, path) in enumerate(zip(self.pq_pairs, self.optimal_path_list)):
            if not path.hp_avg_w_list:
                raise ValueError(
                    f"Axiom 3 (FirstStepIsTheBid) failed: OptimalPathList[{i}] has no steps."
                )
            if path.hp_avg_w_list[0] != pair.quantity_x1000 * to_watts:
                raise ValueError(
                    f"Axiom 3 (FirstStepIsTheBid) failed: OptimalPathList[{i}].HpAvgWList[0] "
                    f"({path.hp_avg_w_list[0]} W) must equal PqPairs[{i}].QuantityX1000 "
                    f"({pair.quantity_x1000 * to_watts} W)."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: PairsDescend
        a. PriceX1000 SHALL strictly decrease along PqPairs.
        b. QuantityX1000 SHALL NOT decrease along PqPairs.
        """
        for a, b in zip(self.pq_pairs, self.pq_pairs[1:]):
            if b.price_x1000 >= a.price_x1000:
                raise ValueError(
                    "Axiom 4 (PairsDescend) clause a failed: PriceX1000 must strictly "
                    f"decrease along PqPairs; got {a.price_x1000} then {b.price_x1000}."
                )
            if b.quantity_x1000 < a.quantity_x1000:
                raise ValueError(
                    "Axiom 4 (PairsDescend) clause b failed: QuantityX1000 must not "
                    f"decrease along PqPairs; got {a.quantity_x1000} then {b.quantity_x1000}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: PathsStartTogether
        Every path's StartUnixS SHALL equal the first path's StartUnixS,
        the slot start of the request answered.
        """
        slot_start = self.optimal_path_list[0].start_unix_s
        for i, path in enumerate(self.optimal_path_list[1:], start=1):
            if path.start_unix_s != slot_start:
                raise ValueError(
                    f"Axiom 5 (PathsStartTogether) failed: OptimalPathList[{i}].StartUnixS "
                    f"({path.start_unix_s}) must equal OptimalPathList[0].StartUnixS ({slot_start})."
                )
        return self
