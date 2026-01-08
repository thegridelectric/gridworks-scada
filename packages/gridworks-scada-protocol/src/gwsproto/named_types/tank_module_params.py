"""Type tank.module.params, version 100"""

from typing import Literal, Optional

from pydantic import BaseModel, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import (
    SpaceheatName,
)


class TankModuleParams(BaseModel):
    """
    Parameters for a  GRIDWORKS__TANKMODULE2 device or a GRIDWORKS__TANKMODULE3 device
    """

    HwUid: str
    ActorNodeName: SpaceheatName
    PicoAB: Optional[str] = None
    CapturePeriodS: PositiveInt
    Samples: PositiveInt
    NumSampleAverages: PositiveInt
    AsyncCaptureDeltaMicroVolts: PositiveInt
    CaptureOffsetS: Optional[float] = None
    TypeName: Literal["tank.module.params"] = "tank.module.params"
    Version: Literal["110"] = "110"

    @model_validator(mode="after")
    def check_pico_a_b(self) -> Self:
        """
        Axiom 1: "If PicoAB exists it must be a or b"
        """
        if self.PicoAB and self.PicoAB not in ["a", "b"]:
            raise ValueError(
                f"Axiom 1: If PicoAB exists it must be a or b, not {self.PicoAB}"
            )

        return self
