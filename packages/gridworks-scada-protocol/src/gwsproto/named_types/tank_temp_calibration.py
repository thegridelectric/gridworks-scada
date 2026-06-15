from typing import Literal

from pydantic import BaseModel

class TankTempCalibration(BaseModel):
    Depth1M: float = 1.0
    Depth1B: int = 0
    Depth2M: float = 1.0
    Depth2B: int = 0
    Depth3M: float = 1.0
    Depth3B: int = 0

    TypeName: Literal["gw1.tank.temp.calibration"] = "gw1.tank.temp.calibration"
    Version: Literal["001"] = "001"