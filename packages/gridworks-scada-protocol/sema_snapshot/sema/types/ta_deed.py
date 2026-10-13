from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import TaValidationState
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCSeconds
from sema_snapshot.sema.property_format import UUID4Str


class TaDeed(SemaType):
    """Sema: https://schemas.electricity.works/types/ta.deed/000"""

    ta_id: UUID4Str
    ta_alias: LeftRightDot
    validation_state: TaValidationState
    validator_alias: LeftRightDot
    issued_s: UTCSeconds
    type_name: Literal["ta.deed"] = "ta.deed"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "TaDeed":
        """
        Axiom 1: SimulatedAssetNeverWorld
        If ValidationState is ValidatedSimulatedAsset, the first segment of TaAlias SHALL
        NOT be "w": a simulated asset holds no deed in the world universe.
        """
        if (
            self.validation_state == "ValidatedSimulatedAsset"
            and self.ta_alias.split(".")[0] == "w"
        ):
            raise ValueError(
                "Axiom 1 (SimulatedAssetNeverWorld) failed: a ValidatedSimulatedAsset "
                f"deed cannot carry a world-universe alias, got TaAlias {self.ta_alias}."
            )
        return self
