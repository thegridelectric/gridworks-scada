from typing import Literal

from pydantic import PositiveFloat, PositiveInt, StrictInt

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class HeatingCurve(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/heating.curve/001"""

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
    RhoTimes100: StrictInt
    IntermediatePowerKw: PositiveFloat
    IntermediateRswtF: PositiveInt
    DdPowerKw: PositiveFloat
    DdRswtF: PositiveInt
    DdRoomTempF: PositiveInt
    DdDeltaTF: PositiveInt
    MaxEwtF: PositiveInt
    MassFlowKgH: PositiveInt
    TypeName: Literal["heating.curve"] = "heating.curve"
    Version: Literal["001"] = "001"
