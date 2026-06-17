from typing import Literal
import math
from pydantic import BaseModel, field_validator

class LinearOneDimensionalCalibration(BaseModel):
    """Sema: https://schemas.electricity.works/types/linear.one.dimensional.calibration/001

    Linear calibration applied to a measurement expressed in the consuming
    derived channel's OutputUnit scaling domain.

    Interpreted as:
        calibrated = M * x + B

    where x is the input first converted into the OutputUnit scaling (e.g.
    FahrenheitX100), M is dimensionless, and B is an integer offset in that same
    OutputUnit scaling (e.g. B = -430 is a -4.30 F offset).
    """
    M: float = 1.0
    B: int = 0
    TypeName: Literal["linear.one.dimensional.calibration"] = "linear.one.dimensional.calibration"
    Version: Literal["001"] = "001"

    @field_validator("M")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("Calibration slope M must be finite")
        return v
