from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.types.old_versions.tank_temp_calibration_000 import (
    TankTempCalibration000,
)
from sema_snapshot.sema.types.tank_temp_calibration_map import TankTempCalibrationMap


class TankTempCalibrationMap000(SemaType):
    """Sema: https://schemas.electricity.works/types/gw1.tank.temp.calibration.map/000"""

    buffer: TankTempCalibration000
    tank: dict[str, TankTempCalibration000]
    type_name: Literal["gw1.tank.temp.calibration.map"] = (
        "gw1.tank.temp.calibration.map"
    )
    version: Literal["000"] = "000"

    def upgrade(self) -> TankTempCalibrationMap:
        """
        - Buffer/Tank now reference gw1.tank.temp.calibration:001 (integer B)
        """
        data = self.model_dump()
        data["buffer"] = self.buffer.upgrade().model_dump()
        data["tank"] = {k: v.upgrade().model_dump() for k, v in self.tank.items()}
        data["version"] = "001"
        return TankTempCalibrationMap.model_validate(data)
