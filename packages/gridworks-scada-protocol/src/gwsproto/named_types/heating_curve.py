from typing import Literal

from pydantic import PositiveFloat, PositiveInt, StrictInt

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class HeatingCurve(GwsprotoSemaType):
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
