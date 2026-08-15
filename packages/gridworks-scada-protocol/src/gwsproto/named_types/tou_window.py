from typing import List, Literal

from pydantic import ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import DayOfWeek
from gwsproto.property_format import HhMm
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class TouWindow(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.tou.window/000"""

    Start: HhMm
    End: HhMm
    Days: List[DayOfWeek]
    TypeName: Literal["gw.tou.window"] = "gw.tou.window"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: WindowOrder.
        Start SHALL be strictly earlier than End. A window SHALL NOT wrap
        midnight; a schedule needing one expresses it as two windows.
        """
        if self.Start >= self.End:
            raise ValueError(
                "Axiom 1 (WindowOrder) failed: Start must be strictly "
                f"earlier than End, got {self.Start} >= {self.End}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: DaysNonEmptyUnique.
        a. Days SHALL be non-empty. b. Days SHALL NOT contain duplicate values.
        """
        if not self.Days:
            raise ValueError(
                "Axiom 2 (DaysNonEmptyUnique) failed: Days must be non-empty."
            )
        if len(self.Days) != len(set(self.Days)):
            raise ValueError(
                "Axiom 2 (DaysNonEmptyUnique) failed: Days must not contain "
                "duplicate values."
            )
        return self
