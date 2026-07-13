from typing import Literal

from pydantic import BaseModel


class CopCurve(BaseModel):
    """Sema: https://schemas.electricity.works/types/cop.curve/000"""

    Intercept: float
    OatCoeff: float
    LwtCoeff: float
    Min: float
    MinOatF: float
    TypeName: Literal["cop.curve"] = "cop.curve"
    Version: Literal["000"] = "000"
