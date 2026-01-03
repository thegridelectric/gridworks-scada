from typing import List

from result import Ok
from result import Result

from actors.config import ScadaSettings
from gwsproto.data_classes.components.electric_meter_component import \
    ElectricMeterComponent
from drivers.driver_result import DriverResult
from drivers.power_meter.power_meter_driver import PowerMeterDriver
from gwsproto.enums import MakeModel, TelemetryName


class UnknownPowerMeterDriver(PowerMeterDriver):
    def __init__(self, component: ElectricMeterComponent, settings: ScadaSettings):
        super(UnknownPowerMeterDriver, self).__init__(component=component, settings=settings)
        if component.cac.MakeModel != MakeModel.UNKNOWNMAKE__UNKNOWNMODEL:
            raise Exception(f"Expected {MakeModel.UNKNOWNMAKE__UNKNOWNMODEL}, got {component.cac}")

    def __repr__(self):
        return "UnknownPowerMeterDriver"

    def read_current_rms_micro_amps(self) -> Result[DriverResult[int | None], Exception]:
        raise NotImplementedError

    def read_hw_uid(self) -> Result[DriverResult[str], Exception]:
        return Ok(DriverResult(""))

    def read_power_w(self) -> Result[DriverResult[int | None], Exception]:
        return Ok(DriverResult(0))

    def telemetry_name_list(self) -> List[TelemetryName]:
        return []
