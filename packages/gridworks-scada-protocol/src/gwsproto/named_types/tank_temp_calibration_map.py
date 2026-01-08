from typing import Literal
from typing_extensions import Self

from pydantic import BaseModel, PositiveInt, model_validator
from gwsproto.named_types.tank_temp_calibration import TankTempCalibration

class TankTempCalibrationMap(BaseModel):
    Buffer: TankTempCalibration
    Tank: dict[PositiveInt, TankTempCalibration]

    TypeName: Literal["gw1.tank.temp.calibration.map"] = "gw1.tank.temp.calibration.map"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1:
        - There are between 1 and 6 tanks
        - Tank indices must be contiguous starting at 1
        """
        tank_indices = sorted(self.Tank.keys())

        num_tanks = len(tank_indices)
        if num_tanks < 1 or num_tanks > 6:
            raise ValueError(
                f"Axiom 1 failed: expected between 1 and 6 tanks, got {num_tanks}"
            )

        expected_indices = list(range(1, num_tanks + 1))
        if tank_indices != expected_indices:
            raise ValueError(
                "Axiom 1 failed: tank indices must be contiguous starting at 1. "
                f"Expected {expected_indices}, got {tank_indices}"
            )

        return self
        
