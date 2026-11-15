from typing import List, Literal, Optional

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit
from gwsproto.named_types.flo_optimal_path import FloOptimalPath
from gwsproto.named_types.flo_path_penalties_bruce import FloPathPenaltiesBruce
from gwsproto.named_types.flo_tank_store_path import FloTankStorePath
from gwsproto.named_types.price_quantity_unitless import PriceQuantityUnitless
from gwsproto.property_format import GitCommit, LeftRightDotStr, NonEmptyString, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloRecommendation(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.recommendation/001"""

    BidderAlias: LeftRightDotStr
    PqPairs: List[PriceQuantityUnitless]
    PriceUnit: MarketPriceUnit
    QuantityUnit: MarketQuantityUnit
    OptimalPathList: List[FloOptimalPath]
    StoreStateList: Optional[List[FloTankStorePath]] = None
    PathPenaltiesList: Optional[List[FloPathPenaltiesBruce]] = None
    FloName: LeftRightDotStr
    FloRepo: NonEmptyString
    FloGitCommit: GitCommit
    CreatedMs: UTCMilliseconds
    TypeName: Literal["flo.recommendation"] = "flo.recommendation"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: AtLeastOnePair.
        PqPairs SHALL have at least one element.
        """
        if len(self.PqPairs) == 0:
            raise ValueError("Axiom 1 (AtLeastOnePair) failed: PqPairs must not be empty.")
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: PathPerPair.
        OptimalPathList SHALL have the same length as PqPairs.
        """
        if len(self.OptimalPathList) != len(self.PqPairs):
            raise ValueError(
                "Axiom 2 (PathPerPair) failed: OptimalPathList "
                f"({len(self.OptimalPathList)}) and PqPairs ({len(self.PqPairs)}) "
                "must have the same length."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: FirstStepIsTheBid.
        For every i, the first element of OptimalPathList[i].HpAvgWList
        SHALL equal PqPairs[i].QuantityX1000 expressed in watts: as is
        when QuantityUnit is AvgkW, times 1000 when it is AvgMW.
        """
        to_watts = 1000 if self.QuantityUnit == MarketQuantityUnit.AvgMW else 1
        for i, (pair, path) in enumerate(zip(self.PqPairs, self.OptimalPathList)):
            if not path.HpAvgWList:
                raise ValueError(
                    f"Axiom 3 (FirstStepIsTheBid) failed: OptimalPathList[{i}] has no steps."
                )
            if path.HpAvgWList[0] != pair.QuantityX1000 * to_watts:
                raise ValueError(
                    f"Axiom 3 (FirstStepIsTheBid) failed: OptimalPathList[{i}].HpAvgWList[0] "
                    f"({path.HpAvgWList[0]} W) must equal PqPairs[{i}].QuantityX1000 "
                    f"({pair.QuantityX1000 * to_watts} W)."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: PairsDescend.
        a. PriceX1000 SHALL strictly decrease along PqPairs.
        b. QuantityX1000 SHALL NOT decrease along PqPairs.
        """
        for a, b in zip(self.PqPairs, self.PqPairs[1:]):
            if b.PriceX1000 >= a.PriceX1000:
                raise ValueError(
                    "Axiom 4 (PairsDescend) clause a failed: PriceX1000 must strictly "
                    f"decrease along PqPairs; got {a.PriceX1000} then {b.PriceX1000}."
                )
            if b.QuantityX1000 < a.QuantityX1000:
                raise ValueError(
                    "Axiom 4 (PairsDescend) clause b failed: QuantityX1000 must not "
                    f"decrease along PqPairs; got {a.QuantityX1000} then {b.QuantityX1000}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: PathsStartTogether.
        Every path's StartUnixS SHALL equal the first path's StartUnixS,
        the slot start of the request answered.
        """
        slot_start = self.OptimalPathList[0].StartUnixS
        for i, path in enumerate(self.OptimalPathList[1:], start=1):
            if path.StartUnixS != slot_start:
                raise ValueError(
                    f"Axiom 5 (PathsStartTogether) failed: OptimalPathList[{i}].StartUnixS "
                    f"({path.StartUnixS}) must equal OptimalPathList[0].StartUnixS ({slot_start})."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> Self:
        """
        Axiom 6: StoreStatePerPath.
        When present, StoreStateList SHALL have the same length as
        OptimalPathList, and each element's step lists SHALL have the
        length of the path at the same index.
        """
        if self.StoreStateList is None:
            return self
        if len(self.StoreStateList) != len(self.OptimalPathList):
            raise ValueError(
                "Axiom 6 (StoreStatePerPath) failed: StoreStateList "
                f"({len(self.StoreStateList)}) and OptimalPathList "
                f"({len(self.OptimalPathList)}) must have the same length."
            )
        for i, (word, path) in enumerate(zip(self.StoreStateList, self.OptimalPathList)):
            n = len(path.StepDurationMinutes)
            if len(word.TopFList) != n:
                raise ValueError(
                    f"Axiom 6 (StoreStatePerPath) failed: StoreStateList[{i}] has "
                    f"{len(word.TopFList)} steps; OptimalPathList[{i}] has {n}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_7(self) -> Self:
        """
        Axiom 7: PenaltiesPerPath.
        When present, PathPenaltiesList SHALL have the same length as
        OptimalPathList, and each element's penalty lists SHALL have the
        length of the path at the same index.
        """
        if self.PathPenaltiesList is None:
            return self
        if len(self.PathPenaltiesList) != len(self.OptimalPathList):
            raise ValueError(
                "Axiom 7 (PenaltiesPerPath) failed: PathPenaltiesList "
                f"({len(self.PathPenaltiesList)}) and OptimalPathList "
                f"({len(self.OptimalPathList)}) must have the same length."
            )
        for i, (word, path) in enumerate(zip(self.PathPenaltiesList, self.OptimalPathList)):
            n = len(path.StepDurationMinutes)
            if len(word.RswtPenaltyUsdList) != n:
                raise ValueError(
                    f"Axiom 7 (PenaltiesPerPath) failed: PathPenaltiesList[{i}] has "
                    f"{len(word.RswtPenaltyUsdList)} steps; OptimalPathList[{i}] has {n}."
                )
        return self
