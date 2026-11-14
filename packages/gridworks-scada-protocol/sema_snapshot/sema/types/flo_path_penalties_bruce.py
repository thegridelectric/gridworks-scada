from typing import Literal, Self
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType


class FloPathPenaltiesBruce(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.path.penalties.bruce/000"""

    rswt_penalty_usd_list: list[StrictFloat]
    stability_penalty_usd_list: list[StrictFloat]
    short_cycle_penalty_usd_list: list[StrictFloat]
    terminal_cost_usd: StrictFloat
    terminal_cost_empty_store_usd: StrictFloat
    path_cost_usd: StrictFloat
    type_name: Literal["flo.path.penalties.bruce"] = "flo.path.penalties.bruce"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: PenaltyListLengths
        RswtPenaltyUsdList, StabilityPenaltyUsdList and
        ShortCyclePenaltyUsdList SHALL have the same length.
        """
        n = len(self.rswt_penalty_usd_list)
        if (
            len(self.stability_penalty_usd_list) != n
            or len(self.short_cycle_penalty_usd_list) != n
        ):
            raise ValueError(
                "Axiom 1 (PenaltyListLengths) failed: RswtPenaltyUsdList "
                f"({n}), StabilityPenaltyUsdList ({len(self.stability_penalty_usd_list)}) "
                f"and ShortCyclePenaltyUsdList ({len(self.short_cycle_penalty_usd_list)}) "
                "must have the same length."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: TerminalCostBound
        TerminalCostUsd SHALL be at most TerminalCostEmptyStoreUsd.
        """
        if self.terminal_cost_usd > self.terminal_cost_empty_store_usd:
            raise ValueError(
                f"Axiom 2 (TerminalCostBound) failed: TerminalCostUsd ({self.terminal_cost_usd}) "
                f"must be at most TerminalCostEmptyStoreUsd ({self.terminal_cost_empty_store_usd})."
            )
        return self
