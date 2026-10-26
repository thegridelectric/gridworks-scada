from typing import Literal, Self
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveInt


class WaterStore(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.water.store/000"""

    total_store_tanks: PositiveInt
    type_name: Literal["gw.water.store"] = "gw.water.store"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: TankCount
        TotalStoreTanks SHALL be at most 6.
        """
        if self.total_store_tanks > 6:
            raise ValueError(
                "Axiom 1 (TankCount) failed: TotalStoreTanks "
                f"({self.total_store_tanks}) must be at most 6."
            )
        return self
