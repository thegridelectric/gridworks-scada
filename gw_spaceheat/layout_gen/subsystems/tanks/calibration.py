from pydantic import BaseModel

from gwsproto.named_types import LinearOneDimensionalCalibration

class TankCalibration(BaseModel):
    depth1: tuple[float, int] = (1.0, 0)
    depth2: tuple[float, int] = (1.0, 0)
    depth3: tuple[float, int] = (1.0, 0)

    def calibration_for_depth(self, depth: int) -> LinearOneDimensionalCalibration:
        m, b = getattr(self, f"depth{depth}")
        return LinearOneDimensionalCalibration(
            M=m,
            B=b,
        )