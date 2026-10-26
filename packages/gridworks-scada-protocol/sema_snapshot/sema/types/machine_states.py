from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import RelayClosedOrOpen
from sema_snapshot.sema.property_format import HandleName
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds


class MachineStates(SemaType):
    """Sema: https://schemas.electricity.works/types/machine.states/000"""

    machine_handle: HandleName
    state_enum: LeftRightDot
    state_list: list[str]
    unix_ms_list: list[UTCMilliseconds]
    type_name: Literal["machine.states"] = "machine.states"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "MachineStates":
        """
        Axiom 1: ListLengthConsistency
        len(StateList) SHALL equal len(UnixMsList).
        """
        if len(self.state_list) != len(self.unix_ms_list):
            raise ValueError(
                "Axiom 1 failed: state_list and unix_ms_list must have equal length."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "MachineStates":
        """
        Axiom 2: RecognizedStateEnumConsistency
        If StateEnum is a recognized GridWorks enum, then all elements of StateList SHALL be
        valid values of that enum.
        """
        if self.state_enum == "relay.closed.or.open":
            valid = set(RelayClosedOrOpen.values())
            if any(state not in valid for state in self.state_list):
                raise ValueError(
                    "Axiom 2 failed: state_list values must be valid relay.closed.or.open values."
                )
        return self
