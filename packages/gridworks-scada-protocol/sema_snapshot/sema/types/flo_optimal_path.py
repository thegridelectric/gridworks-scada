from typing import Literal, Self
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UTCSeconds


class FloOptimalPath(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.optimal.path/000"""

    start_unix_s: UTCSeconds
    step_duration_minutes: list[PositiveInt]
    hp_avg_w_list: list[StrictInt]
    store_wh_list: list[StrictInt]
    type_name: Literal["flo.optimal.path"] = "flo.optimal.path"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: StepListLengths
        StepDurationMinutes, HpAvgWList and StoreWhList SHALL have the same length.
        """
        n = len(self.step_duration_minutes)
        if len(self.hp_avg_w_list) != n or len(self.store_wh_list) != n:
            raise ValueError(
                "Axiom 1 (StepListLengths) failed: StepDurationMinutes "
                f"({n}), HpAvgWList ({len(self.hp_avg_w_list)}) and StoreWhList "
                f"({len(self.store_wh_list)}) must have the same length."
            )
        return self
