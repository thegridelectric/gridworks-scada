from typing import Literal
import math
from pydantic import field_validator

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class LinearOneDimensionalCalibration(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/linear.one.dimensional.calibration/000"""

    M: float
    B: int
    TypeName: Literal["linear.one.dimensional.calibration"] = "linear.one.dimensional.calibration"
    Version: Literal["000"] = "000"

    @field_validator("M")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("Calibration slope M must be finite")
        return v
