from typing import Literal

from pydantic import PositiveFloat, PositiveInt, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class HeatingCurve(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/heating.curve/000"""

    BaselineAlphaTimes10: StrictInt
    BaselineBetaTimes100: StrictInt
    BaselineGammaEx6: StrictInt
    AlphaEx6: StrictInt
    BetaEx6: StrictInt
    GammaEx6: StrictInt
    DeltaEx6: StrictInt
    EpsilonEx6: StrictInt
    ZetaEx6: StrictInt
    EtaEx6: StrictInt
    RhoTimes100: PositiveInt
    IntermediatePowerKw: PositiveFloat
    IntermediateRswtF: PositiveInt
    DdPowerKw: PositiveFloat
    DdRswtF: PositiveInt
    DdRoomTempF: PositiveInt
    DdDeltaTF: PositiveInt
    MaxEwtF: PositiveInt
    MassFlowKgH: PositiveInt
    TypeName: Literal["heating.curve"] = "heating.curve"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: DesignDayRswtIsHottest. DdRswtF SHALL be greater than or equal to IntermediateRswtF."""
        if self.DdRswtF < self.IntermediateRswtF:
            raise ValueError(
                f"Axiom 1 (DesignDayRswtIsHottest) failed: DdRswtF {self.DdRswtF} "
                f"is below IntermediateRswtF {self.IntermediateRswtF}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: DesignDayPowerIsLargest. DdPowerKw SHALL be greater than or equal to IntermediatePowerKw."""
        if self.DdPowerKw < self.IntermediatePowerKw:
            raise ValueError(
                f"Axiom 2 (DesignDayPowerIsLargest) failed: DdPowerKw {self.DdPowerKw} "
                f"is below IntermediatePowerKw {self.IntermediatePowerKw}."
            )
        return self
