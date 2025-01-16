from typing import List, Optional, Tuple

import numpy as np
import serial.rs485
from result import Ok
from result import Result

from actors.config import ScadaSettings
from gwproto.data_classes.components.electric_meter_component import ElectricMeterComponent
from drivers.driver_result import DriverResult
from drivers.power_meter.deprecated_power_meter_driver import DeprecatedPowerMeterDriver
from pymodbus.client.sync import ModbusSerialClient
from gwproto.enums import MakeModel, TelemetryName
from gwproto.data_classes.data_channel import DataChannel

PORT = "/dev/ttyUSB0"
BAUD = 9600


class SchneiderElectricIem3455_PowerMeterDriver(DeprecatedPowerMeterDriver):
    SERIAL_NUMBER_ADDR = 130
    CURRENT_RMS_MICRO_A_ADDR = 3000

    def __init__(self, component: ElectricMeterComponent, settings: ScadaSettings):
        super(SchneiderElectricIem3455_PowerMeterDriver, self).__init__(
            component=component, settings=settings
        )
        if component.cac.MakeModel != MakeModel.SCHNEIDERELECTRIC__IEM3455:
            raise Exception(f"Expected {MakeModel.SCHNEIDERELECTRIC__IEM3455}, got {component.cac}")
        self.component = component
        self.current_rms_micro_amps: Optional[int] = None
        serial_connection = serial.rs485.RS485(port=PORT, baudrate=BAUD)
        serial_connection.rs485_mode = serial.rs485.RS485Settings(
            rts_level_for_tx=False, rts_level_for_rx=True, delay_before_tx=0.0, delay_before_rx=-0.0
        )
        self.client = ModbusSerialClient(method="rtu")
        self.client.socket = serial_connection
        self.client.connect()

    def close_conn(self, _):
        self.client.close()

    def read_register_raw(
        self, reg_addr, bytes_to_read=2, dtype=np.uint16
    ) -> np.ndarray:
        result = self.client.read_holding_registers(
            address=reg_addr - 1, count=bytes_to_read, unit=12
        )
        data_bytes = np.array([result.registers[1], result.registers[0]], dtype=dtype)
        return data_bytes

    def read_register_exp_6(self, reg_addr) -> int:
        data_bytes = self.read_register_raw(reg_addr)
        data_as_float = data_bytes.view(dtype=np.float32)
        return int(10**6 * data_as_float[0])

    def read_current_rms_micro_amps(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        return Ok(DriverResult(self.read_register_exp_6(self.CURRENT_RMS_MICRO_A_ADDR)))

    def read_hw_uid(self) -> Result[DriverResult[str | None], Exception]:
        """returns the serial number of the Schneider Electric meter as a string"""
        data_bytes = self.read_register_raw(self.SERIAL_NUMBER_ADDR, 2, np.uint32)
        return Ok(DriverResult(f"{str(data_bytes[0])}_{str(data_bytes[1])}"))

    def read_power_w(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        raise NotImplementedError

    def telemetry_name_list(self) -> List[TelemetryName]:
        return [TelemetryName.CurrentRmsMicroAmps]