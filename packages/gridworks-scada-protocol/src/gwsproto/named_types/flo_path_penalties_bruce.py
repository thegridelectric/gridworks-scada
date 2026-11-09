from typing import List, Literal

from pydantic import StrictFloat, model_validator
from typing_extensions import Self

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloPathPenaltiesBruce(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.path.penalties.bruce/000"""

    RswtPenaltyUsdList: List[StrictFloat]
    StabilityPenaltyUsdList: List[StrictFloat]
    ShortCyclePenaltyUsdList: List[StrictFloat]
    TerminalCostUsd: StrictFloat
    TerminalCostEmptyStoreUsd: StrictFloat
    PathCostUsd: StrictFloat
    TypeName: Literal["flo.path.penalties.bruce"] = "flo.path.penalties.bruce"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: PenaltyListLengths.
        RswtPenaltyUsdList, StabilityPenaltyUsdList and
        ShortCyclePenaltyUsdList SHALL have the same length.
        """
        n = len(self.RswtPenaltyUsdList)
        if len(self.StabilityPenaltyUsdList) != n or len(self.ShortCyclePenaltyUsdList) != n:
            raise ValueError(
                "Axiom 1 (PenaltyListLengths) failed: RswtPenaltyUsdList "
                f"({n}), StabilityPenaltyUsdList ({len(self.StabilityPenaltyUsdList)}) "
                f"and ShortCyclePenaltyUsdList ({len(self.ShortCyclePenaltyUsdList)}) "
                "must have the same length."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: TerminalCostBound.
        TerminalCostUsd SHALL be at most TerminalCostEmptyStoreUsd.
        """
        if self.TerminalCostUsd > self.TerminalCostEmptyStoreUsd:
            raise ValueError(
                f"Axiom 2 (TerminalCostBound) failed: TerminalCostUsd ({self.TerminalCostUsd}) "
                f"must be at most TerminalCostEmptyStoreUsd ({self.TerminalCostEmptyStoreUsd})."
            )
        return self
