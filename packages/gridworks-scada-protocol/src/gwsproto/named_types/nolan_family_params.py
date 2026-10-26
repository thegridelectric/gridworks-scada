from typing import Literal

from pydantic import PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import SeasonalStorageMode
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class NolanFamilyParams(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.nolan.family.params/000"""

    KeepBufferFull: bool
    SeasonalStorageMode: SeasonalStorageMode
    BufferFullF: PositiveInt
    BufferChargeF: PositiveInt
    TypeName: Literal["gw.nolan.family.params"] = "gw.nolan.family.params"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ChargeBelowFull.
        BufferChargeF SHALL be less than BufferFullF.
        """
        if self.BufferChargeF >= self.BufferFullF:
            raise ValueError(
                "Axiom 1 (ChargeBelowFull) failed: BufferChargeF "
                f"{self.BufferChargeF} is not below BufferFullF {self.BufferFullF}"
            )
        return self
