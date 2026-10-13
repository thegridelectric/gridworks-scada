from typing import Literal
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import ZoneCircuitGovernanceEvent
from sema_snapshot.sema.property_format import HandleName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str


class ZoneCircuitGovernanceCmd(SemaType):
    """Sema: https://schemas.electricity.works/types/zone.circuit.governance.cmd/000"""

    from_handle: HandleName
    to_handle: HandleName
    event: ZoneCircuitGovernanceEvent
    setpoint_f: StrictFloat | None = None
    trigger_id: UUID4Str
    send_time_unix_ms: UTCMilliseconds
    type_name: Literal["zone.circuit.governance.cmd"] = "zone.circuit.governance.cmd"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ZoneCircuitGovernanceCmd":
        """
        Axiom 1: SetpointIffThermostatic
        a. If Event is SwitchToThermostatic, SetpointF SHALL be present. b. If Event is not
        SwitchToThermostatic, SetpointF SHALL be absent.
        """
        if (
            self.event == ZoneCircuitGovernanceEvent.SwitchToThermostatic
            and self.setpoint_f is None
        ):
            raise ValueError(
                "Axiom 1 (SetpointIffThermostatic) failed: Event is "
                "SwitchToThermostatic, so SetpointF SHALL be present."
            )
        if (
            self.event != ZoneCircuitGovernanceEvent.SwitchToThermostatic
            and self.setpoint_f is not None
        ):
            raise ValueError(
                "Axiom 1 (SetpointIffThermostatic) failed: Event is "
                f"{self.event.value}, so SetpointF SHALL be absent."
            )
        return self
