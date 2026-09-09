from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import TaValidationState
from gwsproto.property_format import LeftRightDotStr, UTCSeconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class TaDeed(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/ta.deed/000"""

    TaId: UUID4Str
    TaAlias: LeftRightDotStr
    ValidationState: TaValidationState
    ValidatorAlias: LeftRightDotStr
    IssuedS: UTCSeconds
    TypeName: Literal["ta.deed"] = "ta.deed"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: SimulatedAssetNeverWorld
        If ValidationState is ValidatedSimulatedAsset, the first segment of
        TaAlias SHALL NOT be "w": a simulated asset holds no deed in the
        world universe.
        """
        if (
            self.ValidationState == TaValidationState.ValidatedSimulatedAsset
            and self.TaAlias.split(".")[0] == "w"
        ):
            raise ValueError(
                "Axiom 1 (SimulatedAssetNeverWorld) failed: a ValidatedSimulatedAsset "
                f"deed cannot carry a world-universe alias, got TaAlias {self.TaAlias}."
            )
        return self
