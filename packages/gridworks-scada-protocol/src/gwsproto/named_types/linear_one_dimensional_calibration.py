from typing import Literal
import math
from pydantic import BaseModel, field_validator

class LinearOneDimensionalCalibration(BaseModel):
    """ASL: https://schemas.electricity.works/types/linear.one.dimensional.calibration/000
    
    Linear calibration applied to a raw sensor measurement.

    Interpreted as:
        calibrated_value = M * raw_value + B

    This calibration represents empirical correction of a sensor's
    raw output into a physically meaningful quantity.
    """
    M: float = 1.0
    B: float = 0.0
    TypeName: Literal["linear.one.dimensional.calibration"] = "linear.one.dimensional.calibration"
    Version: Literal["000"] = "000"

    @field_validator("M", "B")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("Calibration parameters must be finite")
        return v