from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import DayOfWeek
from sema_snapshot.sema.property_format import HhMm


class TouWindow(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.tou.window/000"""

    start: HhMm
    end: HhMm
    days: list[DayOfWeek]
    type_name: Literal["gw.tou.window"] = "gw.tou.window"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "TouWindow":
        """
        Axiom 1: WindowOrder
        Start SHALL be strictly earlier than End. A window SHALL NOT wrap midnight; a
        schedule needing one expresses it as two windows.
        """
        if self.start >= self.end:
            raise ValueError(
                "Axiom 1 (WindowOrder) failed: Start must be strictly "
                f"earlier than End, got {self.start} >= {self.end}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "TouWindow":
        """
        Axiom 2: DaysNonEmptyUnique
        a. Days SHALL be non-empty. b. Days SHALL NOT contain duplicate values.
        """
        if not self.days:
            raise ValueError(
                "Axiom 2 (DaysNonEmptyUnique) failed: Days must be non-empty."
            )
        if len(self.days) != len(set(self.days)):
            raise ValueError(
                "Axiom 2 (DaysNonEmptyUnique) failed: Days must not contain "
                "duplicate values."
            )
        return self
