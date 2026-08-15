from typing import Literal, Optional

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import SetpointPhase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SetpointBelief(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/setpoint.belief/000"""

    Phase: SetpointPhase
    ValueF: Optional[float] = None
    TypeName: Literal["setpoint.belief"] = "setpoint.belief"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: UnknownIsValueless.
        a. If Phase is Unknown, ValueF SHALL be absent.
        b. If Phase is not Unknown, ValueF SHALL be present.
        """
        if self.Phase == SetpointPhase.Unknown and self.ValueF is not None:
            raise ValueError(
                "Axiom 1 (UnknownIsValueless) failed: Phase is Unknown but "
                "ValueF is present."
            )
        if self.Phase != SetpointPhase.Unknown and self.ValueF is None:
            raise ValueError(
                "Axiom 1 (UnknownIsValueless) failed: Phase is "
                f"{self.Phase} but ValueF is absent."
            )
        return self
