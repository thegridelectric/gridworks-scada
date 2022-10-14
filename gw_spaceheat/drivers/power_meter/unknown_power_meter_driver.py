from typing import Optional, List
from data_classes.components.electric_meter_component import ElectricMeterComponent
from drivers.power_meter.power_meter_driver import PowerMeterDriver
from schema.enums import MakeModel
from schema.enums import TelemetryName


class UnknownPowerMeterDriver(PowerMeterDriver):
    def __init__(self, component: ElectricMeterComponent):
        super(UnknownPowerMeterDriver, self).__init__(component=component)
        if component.cac.make_model != MakeModel.UNKNOWNMAKE__UNKNOWNMODEL:
            raise Exception(f"Expected {MakeModel.UNKNOWNMAKE__UNKNOWNMODEL}, got {component.cac}")

    def __repr__(self):
        return "UnknownPowerMeterDriver"

    def read_current_rms_micro_amps(self) -> Optional[int]:
        raise NotImplementedError

    def read_hw_uid(self) -> Optional[str]:
        return None

    def read_power_w(self) -> Optional[int]:
        return None

    def telemetry_name_list(self) -> List[TelemetryName]:
        return []
