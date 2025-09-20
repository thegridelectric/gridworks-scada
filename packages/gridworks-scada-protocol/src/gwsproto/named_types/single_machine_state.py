"""Type single.machine.state, version 000"""

from typing import Literal, Optional

from gwproto.property_format import HandleName, LeftRightDotStr, UTCMilliseconds
from pydantic import BaseModel, model_validator
from typing_extensions import Self


class SingleMachineState(BaseModel):
    """
    Intra-scada comms type for sharing the current state of a state machine.
    """

    MachineHandle: HandleName
    StateEnum: LeftRightDotStr
    State: str
    UnixMs: UTCMilliseconds
    Cause: Optional[str] = None
    TypeName: Literal["single.machine.state"] = "single.machine.state"
    Version: str = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: If StateEnum is a recongized enum, then State is a value of that enum.

        """
        # Implement check for axiom 1"
        return self
