from typing import Literal, Optional

from pydantic import PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import PicoBoardVariant
from gwsproto.property_format import (
    SpaceheatName,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class TankModuleParams(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/tank.module.params/200"""

    HwUid: str
    ActorNodeName: SpaceheatName
    PicoAB: Optional[str] = None
    CapturePeriodS: PositiveInt
    Samples: PositiveInt
    NumSampleAverages: PositiveInt
    AsyncCaptureDeltaMicroVolts: PositiveInt
    CaptureOffsetS: Optional[float] = None
    PicoBoardVariant: PicoBoardVariant
    MicropythonVersion: str
    TypeName: Literal["tank.module.params"] = "tank.module.params"
    Version: Literal["200"] = "200"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: PicoABIsAOrB
        If PicoAB is present it SHALL be "a" or "b".
        """
        if self.PicoAB is not None and self.PicoAB not in ("a", "b"):
            raise ValueError(
                f"Axiom 1 (PicoABIsAOrB) failed: PicoAB must be a or b, not {self.PicoAB!r}"
            )
        return self
