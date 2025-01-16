import logging
from abc import ABC, abstractmethod
from typing import Optional

from gwproactor.logger import LoggerOrAdapter
from gwproto.named_types import ElectricMeterChannelConfig
from result import Err
from result import Ok
from result import Result

from actors.config import ScadaSettings
from gwproto.data_classes.data_channel import DataChannel
from gwproto.data_classes.components.electric_meter_component import \
    ElectricMeterComponent
from drivers.driver_result import DriverResult
from gwproto.enums import TelemetryName


class DeprecatedPowerMeterDriver(ABC):
    component: ElectricMeterComponent
    settings: ScadaSettings
    logger: LoggerOrAdapter

    def __init__(
        self,
        component: ElectricMeterComponent,
        settings: ScadaSettings,
        logger: Optional[LoggerOrAdapter] = None,
    ):
        if not isinstance(component, ElectricMeterComponent):
            raise Exception(f"ElectricMeterDriver requires ElectricMeterComponent. Got {component}")
        self.component = component
        self.settings: ScadaSettings = settings
        self.logger = logger or logging.getLogger(settings.logging.base_log_name)

    def start(self) -> Result[DriverResult, Exception]:
        return Ok(DriverResult(True))

    @abstractmethod
    def read_hw_uid(self) -> Result[DriverResult[str | None], Exception]:
        raise NotImplementedError()

    @abstractmethod
    def read_current_rms_micro_amps(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        raise NotImplementedError()

    @abstractmethod
    def read_power_w(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        raise NotImplementedError()

    def read_telemetry_value(
        self,
        channel: DataChannel
    ) -> Result[DriverResult[int | None], Exception]:
        if channel.TelemetryName == TelemetryName.PowerW:
            return self.read_power_w(channel)
        elif channel.TelemetryName == TelemetryName.CurrentRmsMicroAmps:
            return self.read_current_rms_micro_amps(channel)
        else:
            return Err(ValueError(f"Driver {self} not set up to read {channel.TelemetryName}"))

    def validate_config(self, config: ElectricMeterChannelConfig) -> None:
        ...