from typing import Literal
from pydantic import BaseModel
class LinearOneDimensionalCalibration(BaseModel):
    """Sema: https://schemas.electricity.works/types/linear.one.dimensional.calibration/001"""
    M: float = 1.0
    B: int = 0
    TypeName: Literal["linear.one.dimensional.calibration"] = "linear.one.dimensional.calibration"
    Version: Literal["001"] = "001"
