from typing import Dict
from typing import List

from gwproto.data_classes.components import Ads111xBasedComponent
from result import Ok
from result import Result

from actors.config import ScadaSettings
from drivers.driver_result import DriverResult
from gwproto.data_classes.data_channel import DataChannel
from drivers.multipurpose_sensor.multipurpose_sensor_driver import (
    MultipurposeSensorDriver,
)


class UnknownMultipurposeSensorDriver(MultipurposeSensorDriver):
    def __init__(self, component: Ads111xBasedComponent, settings: ScadaSettings):
        super().__init__(
            component=component, settings=settings
        )

    def __repr__(self):
        return "UnknownMultipurposeSensorDriver"

    def read_telemetry_values(self, channel_telemetry_list: List[DataChannel]) -> Result[
            DriverResult[Dict[DataChannel, int]], Exception]:
        return Ok(DriverResult[Dict[DataChannel, int]]({}))

