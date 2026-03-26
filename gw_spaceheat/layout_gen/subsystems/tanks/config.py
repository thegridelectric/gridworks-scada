from pydantic import BaseModel, Field
from gwsproto.enums import TempCalcMethod

from layout_gen.subsystems.tanks.calibration import TankCalibration

class TankId(BaseModel):
    serial_number: str
    pico_hw_uid: str
    sensor_order: list[int] | None = None

class TankOps(BaseModel):
    capture_period_s: int = 60
    async_capture_delta_micro_volts: int = 2000
    samples: int = 1000
    num_sample_averages: int = 30
    enabled: bool = True
    send_micro_volts: bool = True
    temp_calc: TempCalcMethod = TempCalcMethod.SimpleBeta
    thermistor_beta: int = 3977


class TankConfig(BaseModel):
    id: TankId
    ops: TankOps = Field(default_factory=TankOps)
    cal: TankCalibration = Field(default_factory=TankCalibration)


class TanksConfig(BaseModel):
    buffer: TankConfig
    store: dict[int, TankConfig]