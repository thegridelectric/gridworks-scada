from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.types.tank_temp_calibration import TankTempCalibration


class TankTempCalibrationMap(SemaType):
    """Sema: https://schemas.electricity.works/types/gw1.tank.temp.calibration.map/001"""

    buffer: TankTempCalibration
    tank: dict[str, TankTempCalibration]
    type_name: Literal["gw1.tank.temp.calibration.map"] = (
        "gw1.tank.temp.calibration.map"
    )
    version: Literal["001"] = "001"
