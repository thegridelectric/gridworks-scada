from typing import Literal
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import SetpointPhase


class SetpointBelief(SemaType):
    """Sema: https://schemas.electricity.works/types/setpoint.belief/000"""

    phase: SetpointPhase
    value_f: StrictFloat | None = None
    type_name: Literal["setpoint.belief"] = "setpoint.belief"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "SetpointBelief":
        """
        Axiom 1: UnknownIsValueless
        a. If Phase is Unknown, ValueF SHALL be absent. b. If Phase is not Unknown, ValueF
        SHALL be present.
        """
        if self.phase == SetpointPhase.Unknown and self.value_f is not None:
            raise ValueError(
                "Axiom 1 (UnknownIsValueless) failed: Phase is Unknown, "
                f"so ValueF SHALL be absent; got {self.value_f}."
            )
        if self.phase != SetpointPhase.Unknown and self.value_f is None:
            raise ValueError(
                "Axiom 1 (UnknownIsValueless) failed: Phase is "
                f"{self.phase.value}, so ValueF SHALL be present."
            )
        return self
