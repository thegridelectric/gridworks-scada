from typing import Literal

from pydantic import BaseModel, PositiveFloat, PositiveInt, StrictInt


class HeatingCurve(BaseModel):
    """Sema: https://schemas.electricity.works/types/heating.curve/000"""

    AlphaTimes10: StrictInt
    BetaTimes100: StrictInt
    GammaEx6: StrictInt
    IntermediatePowerKw: PositiveFloat
    IntermediateRswtF: PositiveInt
    DdPowerKw: PositiveFloat
    DdRswtF: PositiveInt
    DdDeltaTF: PositiveInt
    MaxEwtF: PositiveInt
    TypeName: Literal["heating.curve"] = "heating.curve"
    Version: Literal["000"] = "000"
