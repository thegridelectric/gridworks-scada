from pydantic import BaseModel

from gwsproto.named_types import LinearOneDimensionalCalibration

class TankCalibration(BaseModel):
    depth1: tuple[float, int]
    depth2: tuple[float, int]
    depth3: tuple[float, int]

    def calibration_for_depth(self, depth: int) -> LinearOneDimensionalCalibration:
        m, b = getattr(self, f"depth{depth}")
        return LinearOneDimensionalCalibration(
            M=m,
            B=b,
        )