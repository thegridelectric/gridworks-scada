from typing import Literal

from pydantic import StrictInt

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class Ha1Params(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/ha1.params/006
    """

    AlphaTimes10: StrictInt
    BetaTimes100: StrictInt
    GammaEx6: StrictInt
    IntermediatePowerKw: float
    IntermediateRswtF: StrictInt
    DdPowerKw: float
    DdRswtF: StrictInt
    DdDeltaTF: StrictInt
    HpMaxKwEl: float
    MaxEwtF: StrictInt
    LoadOverestimationPercent: StrictInt
    CopIntercept: float
    CopOatCoeff: float
    CopLwtCoeff: float
    CopMin: float
    CopMinOatF: float
    HpTurnOnMinutes: StrictInt = 12
    TypeName: Literal["ha1.params"] = "ha1.params"
    Version: str = "006"
