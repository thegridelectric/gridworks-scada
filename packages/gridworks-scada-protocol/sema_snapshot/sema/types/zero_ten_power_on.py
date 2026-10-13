from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import SpaceheatName


class ZeroTenPowerOn(SemaType):
    """Sema: https://schemas.electricity.works/types/zero.ten.power.on/000"""

    node_name: SpaceheatName
    power_on_volts_times_ten: NonNegativeInt
    type_name: Literal["zero.ten.power.on"] = "zero.ten.power.on"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ZeroTenPowerOn":
        """
        Axiom 1: TenVoltCeiling
        PowerOnVoltsTimesTen SHALL be at most 100.
        """
        if self.power_on_volts_times_ten > 100:
            raise ValueError(
                "Axiom 1 (TenVoltCeiling) failed: PowerOnVoltsTimesTen "
                f"{self.power_on_volts_times_ten} exceeds 100."
            )
        return self
