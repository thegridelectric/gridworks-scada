from typing import Literal, Optional

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class BoilerBackup(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.boiler.backup/001"""

    FailsafeRelayName: Optional[SpaceheatName] = None
    InterceptRelayName: SpaceheatName
    InService: bool
    TypeName: Literal["gw.boiler.backup"] = "gw.boiler.backup"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: DistinctRelays. Where FailsafeRelayName is present, it SHALL
        NOT equal InterceptRelayName.
        """
        if (
            self.FailsafeRelayName is not None
            and self.FailsafeRelayName == self.InterceptRelayName
        ):
            raise ValueError(
                "Axiom 1 (DistinctRelays) failed: FailsafeRelayName and "
                f"InterceptRelayName are both {self.FailsafeRelayName}."
            )
        return self
