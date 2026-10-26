from typing import Literal

from pydantic import PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class WaterStore(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.water.store/000"""

    TotalStoreTanks: PositiveInt
    TypeName: Literal["gw.water.store"] = "gw.water.store"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: TankCount. TotalStoreTanks SHALL be at most 6.
        """
        if self.TotalStoreTanks > 6:
            raise ValueError(
                "Axiom 1 (TankCount) failed: TotalStoreTanks "
                f"({self.TotalStoreTanks}) must be at most 6."
            )
        return self
