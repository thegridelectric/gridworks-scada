from typing import List, Literal

from pydantic import PositiveInt, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import UTCSeconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloOptimalPath(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.optimal.path/000"""

    StartUnixS: UTCSeconds
    StepDurationMinutes: List[PositiveInt]
    HpAvgWList: List[StrictInt]
    StoreWhList: List[StrictInt]
    TypeName: Literal["flo.optimal.path"] = "flo.optimal.path"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: StepListLengths.
        StepDurationMinutes, HpAvgWList and StoreWhList SHALL have the same length.
        """
        n = len(self.StepDurationMinutes)
        if len(self.HpAvgWList) != n or len(self.StoreWhList) != n:
            raise ValueError(
                "Axiom 1 (StepListLengths) failed: StepDurationMinutes "
                f"({n}), HpAvgWList ({len(self.HpAvgWList)}) and StoreWhList "
                f"({len(self.StoreWhList)}) must have the same length."
            )
        return self
