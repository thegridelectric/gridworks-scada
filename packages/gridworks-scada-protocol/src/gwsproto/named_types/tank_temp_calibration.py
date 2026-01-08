from typing import Literal

from pydantic import BaseModel

class TankTempCalibration(BaseModel):
    Depth1M: float = 1.0
    Depth1B: float = 0.0
    Depth2M: float = 1.0
    Depth2B: float = 0.0
    Depth3M: float = 1.0
    Depth3B: float = 0.0

    TypeName: Literal["gw1.tank.temp.calibration"] = "gw1.tank.temp.calibration"
    Version: Literal["000"] = "000"