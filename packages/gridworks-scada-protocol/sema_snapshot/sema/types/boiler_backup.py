from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import SpaceheatName


class BoilerBackup(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.boiler.backup/001"""

    failsafe_relay_name: SpaceheatName | None = None
    intercept_relay_name: SpaceheatName
    in_service: bool
    type_name: Literal["gw.boiler.backup"] = "gw.boiler.backup"
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "BoilerBackup":
        """
        Axiom 1: DistinctRelays
        Where FailsafeRelayName is present, it SHALL NOT equal
        InterceptRelayName.
        """
        if (
            self.failsafe_relay_name is not None
            and self.failsafe_relay_name == self.intercept_relay_name
        ):
            raise ValueError(
                "Axiom 1 (DistinctRelays) failed: FailsafeRelayName and "
                f"InterceptRelayName are both {self.failsafe_relay_name}."
            )
        return self
