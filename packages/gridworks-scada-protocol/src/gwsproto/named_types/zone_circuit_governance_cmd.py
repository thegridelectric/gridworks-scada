from typing import Literal, Optional

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.enums import ZoneCircuitGovernanceEvent
from gwsproto.property_format import HandleName, UTCMilliseconds, UUID4Str


class ZoneCircuitGovernanceCmd(BaseModel):
    """Sema: https://schemas.electricity.works/types/zone.circuit.governance.cmd/000"""

    FromHandle: HandleName
    ToHandle: HandleName
    Event: ZoneCircuitGovernanceEvent
    SetpointF: Optional[float] = None
    TriggerId: UUID4Str
    SendTimeUnixMs: UTCMilliseconds
    TypeName: Literal["zone.circuit.governance.cmd"] = "zone.circuit.governance.cmd"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: SetpointIffThermostatic.
        a. If Event is SwitchToThermostatic, SetpointF SHALL be present.
        b. If Event is not SwitchToThermostatic, SetpointF SHALL be absent.
        """
        thermostatic = self.Event == ZoneCircuitGovernanceEvent.SwitchToThermostatic
        if thermostatic and self.SetpointF is None:
            raise ValueError(
                "Axiom 1 (SetpointIffThermostatic) failed: Event is "
                "SwitchToThermostatic but SetpointF is absent."
            )
        if not thermostatic and self.SetpointF is not None:
            raise ValueError(
                "Axiom 1 (SetpointIffThermostatic) failed: Event is "
                f"{self.Event} but SetpointF is present."
            )
        return self
