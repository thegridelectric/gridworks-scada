from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.property_format import NonNegativeInt, SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ZeroTenPowerOn(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/zero.ten.power.on/000"""

    NodeName: SpaceheatName
    PowerOnVoltsTimesTen: NonNegativeInt
    TypeName: Literal["zero.ten.power.on"] = "zero.ten.power.on"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: TenVoltCeiling.
        PowerOnVoltsTimesTen SHALL be at most 100.
        """
        if self.PowerOnVoltsTimesTen > 100:
            raise ValueError(
                "Axiom 1 (TenVoltCeiling) failed: PowerOnVoltsTimesTen "
                f"{self.PowerOnVoltsTimesTen} exceeds 100."
            )
        return self
