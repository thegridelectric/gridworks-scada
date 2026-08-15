
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from typing import Literal



class CopCurve(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/cop.curve/000"""

    Intercept: float
    OatCoeff: float
    LwtCoeff: float
    Min: float
    MinOatF: float
    TypeName: Literal["cop.curve"] = "cop.curve"
    Version: Literal["000"] = "000"
