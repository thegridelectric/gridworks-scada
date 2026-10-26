from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class BoilerBackup(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.boiler.backup/000"""

    FailsafeRelayName: SpaceheatName
    AquastatCtrlRelayName: SpaceheatName
    InService: bool
    TypeName: Literal["gw.boiler.backup"] = "gw.boiler.backup"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: DistinctRelays. FailsafeRelayName SHALL NOT equal
        AquastatCtrlRelayName.
        """
        if self.FailsafeRelayName == self.AquastatCtrlRelayName:
            raise ValueError(
                "Axiom 1 (DistinctRelays) failed: FailsafeRelayName and "
                f"AquastatCtrlRelayName are both {self.FailsafeRelayName}."
            )
        return self
