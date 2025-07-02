import contextlib
import logging
import serial
import time
import struct
from typing import Any
from typing import Optional

from gwproactor.logger import LoggerOrAdapter
# from gwproto.named_types import ElectricMeterChannelConfig
from result import Ok
from result import Result

from actors.config import ScadaSettings
from gwproto.data_classes.data_channel import DataChannel
from gwproto.data_classes.components.electric_meter_component import ElectricMeterComponent
from drivers.driver_result import DriverResult
from drivers.exceptions import DriverWarning
from drivers.power_meter.power_meter_driver import PowerMeterDriver

# --------------------------
from typing import Literal
from pydantic import BaseModel, Field

class EkmConfig(BaseModel):
    TypeName: Literal["ekm.register.config"] = "ekm.register.config"
    Version: Literal["000"] = "000"

from typing import Literal, Optional
from gwproto.named_types.channel_config import ChannelConfig
from gwproto.named_types.egauge_register_config import (
    EgaugeRegisterConfig as EgaugeConfig,
)

class ElectricMeterChannelConfig(ChannelConfig):
    EgaugeRegisterConfig: Optional[EgaugeConfig] = None
    EkmRegisterConfig: Optional[EkmConfig] = None
    TypeName: Literal["electric.meter.channel.config"] = "electric.meter.channel.config"
    Version: Literal["000"] = "000"

# --------------------------

class EkmReadFailed(DriverWarning):
    meter_number: str
    command: bytes
    response: bytes
    error_msg: str

    def __init__(
            self,
            meter_number: str,
            command: bytes,
            response: bytes,
            error_msg: str = "",
    ):
        super().__init__(error_msg)
        self.meter_number = meter_number
        self.command = command
        self.response = response
        self.error_msg = error_msg

    def __str__(self):
        s = self.__class__.__name__
        super_str = super().__str__()
        if super_str:
            s += f" <{super_str}>"
        s += (
            f"  meter_number: {self.meter_number}  "
            f"  command: {self.command.hex()}  "
            f"  response: {self.response.hex() if self.response else 'None'}\n"
            f"  error: {self.error_msg}"
        )
        return s

class EkmReadOutOfRange(EkmReadFailed):
    ...

class EkmCommWarning(DriverWarning):
    ...

class EkmHadDisconnect(EkmCommWarning):
    ...

class EkmConstructionFailed(EkmCommWarning):
    ...

class EkmConnectFailed(EkmCommWarning):
    ...

class TryConnectResult(DriverResult[bool | None]):
    skipped_for_backoff: bool = False

    def __init__(
        self,
        connected: bool,
        warnings: Optional[list[Exception]] = None,
        skipped_for_backoff: bool = False,
    ):
        super().__init__(value=True if connected else None, warnings=warnings)
        self.skipped_for_backoff = skipped_for_backoff

    @property
    def connected(self) -> bool:
        return bool(self.value)

    def __bool__(self) -> bool:
        return self.connected

    @property
    def had_disconnect(self) -> bool:
        return any(type(warning) == EkmHadDisconnect for warning in self.warnings)

    def __str__(self) -> str:
        s = (
            f"TryConnectResult connected: {self.connected}  "
            f"had_disconnected: {self.had_disconnect}  "
            f"skipped: {self.skipped_for_backoff}  warnings: {len(self.warnings)}"
        )
        for warning in self.warnings:
            s += f"\n  type: <{type(warning)}>  warning: <{warning}>"
        return s

class Ekm_Omnimeter_PowerMeterDriver(PowerMeterDriver):
    MAX_RECONNECT_DELAY_SECONDS: float = 10
    CLIENT_TIMEOUT: float = 5.0
    DEFAULT_BAUDRATE: int = 9600
    DEFAULT_PORT: str = '/dev/ttyACM0'

    _serial_client: Optional[serial.Serial] = None
    _curr_connect_delay = 0.5
    _last_connect_time: float = 0.0
    _meter_number: str = "000300015310"  # Default meter number, should be configurable

    def __init__(self, component: ElectricMeterComponent, settings: ScadaSettings, logger: LoggerOrAdapter):
        super().__init__(component, settings, logger=logger)
        # TODO: read meter number from component
        # self._meter_number = getattr(component.gt, 'MeterNumber', self._meter_number)

    def clean_client(self):
        if self._serial_client is not None:
            with contextlib.suppress(Exception):
                self._serial_client.close()
            self._serial_client = None

    def client_is_open(self) -> bool:
        return self._serial_client is not None and self._serial_client.is_open

    def try_connect(self, first_time: bool = False) -> Result[TryConnectResult, Exception]:
        now = time.time()
        comm_warnings = []
        skip_for_backoff = False
        path_dbg = 0
        
        if not self.client_is_open():
            path_dbg |= 0x00000001
            if (
                self._curr_connect_delay <= 0.0
                and not first_time
                and self._serial_client is not None
            ):
                path_dbg |= 0x00000002
                comm_warnings.append(EkmHadDisconnect())
            self.clean_client()
            skip_for_backoff = (now - self._last_connect_time) <= self._curr_connect_delay
            if not skip_for_backoff:
                path_dbg |= 0x00000004
                if self._curr_connect_delay <= 0.0:
                    path_dbg |= 0x00000008
                    self._curr_connect_delay = 0.5
                else:
                    path_dbg |= 0x00000010
                    self._curr_connect_delay = min(
                        self._curr_connect_delay * 2,
                        self.MAX_RECONNECT_DELAY_SECONDS
                    )
                self._last_connect_time = now
                try:
                    self._serial_client = serial.Serial(
                        port=self.DEFAULT_PORT,
                        baudrate=self.DEFAULT_BAUDRATE,
                        parity=serial.PARITY_EVEN,
                        stopbits=serial.STOPBITS_ONE,
                        bytesize=serial.SEVENBITS,
                        xonxoff=0,
                        timeout=self.CLIENT_TIMEOUT
                    )
                except Exception as e:
                    path_dbg |= 0x00000020
                    comm_warnings.append(e)
                    comm_warnings.append(EkmConstructionFailed())
                    self.clean_client()
                else:
                    path_dbg |= 0x00000040
                    if not self.client_is_open():
                        path_dbg |= 0x00000100
                        comm_warnings.append(EkmConnectFailed())
                        self.clean_client()
        
        if self.client_is_open():
            path_dbg |= 0x00000200
            self._last_connect_time = now
            self._curr_connect_delay = 0.0
            
        result = Ok(
            TryConnectResult(
                connected=self.client_is_open(),
                warnings=comm_warnings,
                skipped_for_backoff=skip_for_backoff
            )
        )
        if not result.value.connected or result.value.warnings:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.info(f"TryConnectResult:\n{result.value}")
                log_path = True
            elif self.logger.isEnabledFor(logging.INFO) and result.value.warnings:
                log_path = True
            else:
                log_path = False
            if log_path:
                self.logger.info(f"--Ekm.try_connect  path:0x{path_dbg:08x}")
        return result

    def start(self) -> Result[DriverResult[TryConnectResult], Exception]:
        return self.try_connect(first_time=True)

    def _send_request_a(self) -> Result[DriverResult[dict], Exception]:
        """Send Request A to v4 Meter and parse response"""
        if not self.client_is_open():
            return Ok(DriverResult(None, [EkmConnectFailed()]))
        
        try:
            # Send Request A to v4 Meter
            command = b"\x2F\x3F" + self._meter_number.encode() + b"\x30\x30\x21\x0D\x0A"
            self._serial_client.write(command)
            
            # Get meter response
            response = self._serial_client.read(255)
            
            if not response:
                return Ok(DriverResult(
                    None, 
                    [EkmReadFailed(
                        meter_number=self._meter_number,
                        command=command,
                        response=b"",
                        error_msg="No response received"
                    )]
                ))
            
            # Parse the response using the same logic as in ekm_omnimeter_get_reading.py
            key_byte_lengths = [
                ("Packet Source", 1, False),
                ("Meter Model", 2, False),
                ("Firmware Version", 1, False),
                ("Meter Number", 12, True),
                ("Kilowatt Hour Total", 8, True),
                ("Reactive Energy Total", 8, True),
                ("Rev Kilowatt Hour Total", 8, True),
                ("Kilowatt Hour L1", 8, True),
                ("Kilowatt Hour L2", 8, True),
                ("Kilowatt Hour L3", 8, True),
                ("Reverse Kilowatt Hour L1", 8, True),
                ("Reverse Kilowatt Hour L2", 8, True),
                ("Reverse Kilowatt Hour L3", 8, True),
                ("Resettable Kilowatt Hour Total", 8, True),
                ("Resettable Reverse Kilowatt Hour Total", 8, True),
                ("RMS Volts L1", 4, True),
                ("RMS Volts L2", 4, True),
                ("RMS Volts L3", 4, True),
                ("Amps L1", 5, True),
                ("Amps L2", 5, True),
                ("Amps L3", 5, True),
                ("RMS Watts L1", 7, True),
                ("RMS Watts L2", 7, True),
                ("RMS Watts L3", 7, True),
                ("RMS Total Watts", 7, True),
                ("Cos Theta L1", 4, True),
                ("Cos Theta L2", 4, True),
                ("Cos Theta L3", 4, True),
                ("Reactive Power L1", 7, True),
                ("Reactive Power L2", 7, True),
                ("Reactive Power L3", 7, True),
                ("Reactive Power Total", 7, True),
                ("Line Frequency", 4, True),
                ("Pulse Count 1", 8, True),
                ("Pulse Count 2", 8, True),
                ("Pulse Count 3", 8, True),
                ("Pulse Input State", 1, True),
                ("Current Direction", 1, True),
                ("Outputs", 1, True),
                ("Kilowatt Hour Decimal Places", 1, True),
                ("Reserved", 2, True),
                ("Date and Time", 14, True)
            ]
            
            # Calculate total payload length
            payload_length = sum(length for _, length, _ in key_byte_lengths)
            payload = response[:payload_length]
            
            # Parse and decode all values
            values = []
            offset = 0
            for key, length, as_ascii in key_byte_lengths:
                segment = payload[offset:offset + length]
                if as_ascii:
                    try:
                        value = segment.decode('ascii').strip()
                    except UnicodeDecodeError:
                        value = "<decode error>"
                else:
                    value = int.from_bytes(segment, byteorder='big')
                values.append(value)
                offset += length
            
            result_dict = {key: value for (key, _, _), value in zip(key_byte_lengths, values)}
            
            # Format date and time
            date_time = result_dict['Date and Time']
            if len(date_time) >= 14:
                date = f"20{date_time[:2]}-{date_time[2:4]}-{date_time[4:6]}"
                timing = f"{date_time[8:10]}:{date_time[10:12]}:{date_time[12:14]}"
                result_dict["Date and Time"] = f"{date} {timing} (UTC-{date_time[6:8]})"
            
            return Ok(DriverResult(result_dict))
            
        except Exception as e:
            return Ok(DriverResult(
                None,
                [EkmReadFailed(
                    meter_number=self._meter_number,
                    command=command if 'command' in locals() else b"",
                    response=response if 'response' in locals() else b"",
                    error_msg=str(e)
                )]
            ))

    def read_hw_uid(self) -> Result[DriverResult[str | None], Exception]:
        connect_result = self.try_connect()
        if connect_result.is_ok() and connect_result.value.connected:
            read_result = self._send_request_a()
            if read_result.is_ok() and read_result.value.value is not None:
                meter_data = read_result.value.value
                meter_number = meter_data.get("Meter Number", self._meter_number)
                return Ok(DriverResult(meter_number, read_result.value.warnings))
            else:
                return read_result
        else:
            return connect_result

    def read_power_w(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        connect_result = self.try_connect()
        if connect_result.is_ok() and connect_result.value.connected:
            read_result = self._send_request_a()
            driver_result: DriverResult[int | None] = DriverResult(None, connect_result.value.warnings)
            
            if read_result.is_ok() and read_result.value.value is not None:
                meter_data = read_result.value.value
                driver_result.warnings.extend(read_result.value.warnings)
                
                # Determine which power reading to use based on channel configuration
                # Default to RMS Total Watts, but could be configured per channel
                power_key = "RMS Total Watts"  # Could be made configurable
                
                if power_key in meter_data:
                    try:
                        power_value = int(meter_data[power_key])
                        if not is_short_integer(power_value):
                            unclipped_int_power = power_value
                            MIN_POWER = -2**15
                            MAX_POWER = 2**15 - 1
                            power_value = max(MIN_POWER, min(power_value, MAX_POWER))
                            driver_result.warnings.append(
                                EkmReadOutOfRange(
                                    meter_number=self._meter_number,
                                    command=b"",
                                    response=b"",
                                    msg=f"Power value {unclipped_int_power} clipped to [{MIN_POWER}, {MAX_POWER}] result: {power_value}",
                                )
                            )
                        driver_result.value = power_value
                    except (ValueError, TypeError):
                        driver_result.warnings.append(
                            EkmReadFailed(
                                meter_number=self._meter_number,
                                command=b"",
                                response=b"",
                                error_msg=f"Could not convert {power_key} value '{meter_data[power_key]}' to integer"
                            )
                        )
                else:
                    driver_result.warnings.append(
                        EkmReadFailed(
                            meter_number=self._meter_number,
                            command=b"",
                            response=b"",
                            error_msg=f"Power key '{power_key}' not found in meter data"
                        )
                    )
            else:
                driver_result.warnings.extend(read_result.value.warnings if read_result.is_ok() else [])
                
            return Ok(driver_result)
        else:
            return connect_result

    def read_current_rms_micro_amps(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        raise NotImplementedError

    def validate_config(self, config: ElectricMeterChannelConfig) -> None:
        if not hasattr(config, 'EkmRegisterConfig'):
            raise ValueError("Misconfigured EkmRegisterConfig for power meter. EkmRegisterConfig is missing.")

    def __del__(self):
        self.clean_client()


def is_short_integer(candidate: int) -> bool:
    try:
        struct.pack("h", candidate)
    except:  # noqa
        return False
    return True