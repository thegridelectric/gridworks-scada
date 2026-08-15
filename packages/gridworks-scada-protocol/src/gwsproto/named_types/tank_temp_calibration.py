
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from typing import Literal



class TankTempCalibration(GwsprotoSemaType):
    Depth1M: float = 1.0
    Depth1B: int = 0
    Depth2M: float = 1.0
    Depth2B: int = 0
    Depth3M: float = 1.0
    Depth3B: int = 0

    TypeName: Literal["gw1.tank.temp.calibration"] = "gw1.tank.temp.calibration"
    Version: Literal["001"] = "001"