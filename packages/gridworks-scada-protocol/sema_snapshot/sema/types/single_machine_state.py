from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import RelayClosedOrOpen
from sema_snapshot.sema.property_format import HandleName
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds


class SingleMachineState(SemaType):
    """Sema: https://schemas.electricity.works/types/single.machine.state/000"""

    machine_handle: HandleName
    state_enum: LeftRightDot
    state: str
    unix_ms: UTCMilliseconds
    cause: str | None = None
    type_name: Literal["single.machine.state"] = "single.machine.state"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "SingleMachineState":
        """
        Axiom 1: RecognizedStateEnumConsistency
        If StateEnum equals "relay.closed.or.open", then State SHALL equal "RelayClosed" or
        "RelayOpen". More generally, if StateEnum is a recognized GridWorks enum, then State
        SHALL be a valid value of that enum.
        """
        if (
            self.state_enum == "relay.closed.or.open"
            and self.state not in RelayClosedOrOpen.values()
        ):
            raise ValueError(
                "Axiom 1 failed: state must be a valid relay.closed.or.open value."
            )
        return self
