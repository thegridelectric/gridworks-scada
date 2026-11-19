from actors.config import ScadaSettings
from drivers.driver_result import DriverResult
from drivers.exceptions import DriverWarning
from drivers.power_meter.power_meter_driver import PowerMeterDriver
from gwsproto.data_classes.components.electric_meter_component import (
    ElectricMeterComponent,
)
from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.enums import SimDeviceType
from plant_link import PlantLink
from result import Ok, Result


class PlantSilent(DriverWarning): ...


class PlantLink_PowerMeterDriver(PowerMeterDriver):
    """A simulated meter: each channel reads its value in the plant's latest
    flux. A channel the plant does not show reads no value, and so does
    every channel while the plant is silent, with a warning, as a meter
    that cannot be reached does."""

    def __init__(
        self, component: ElectricMeterComponent, settings: ScadaSettings, link: PlantLink
    ) -> None:
        super().__init__(component=component, settings=settings)
        if component.gt.DeviceType != SimDeviceType.SimPowerMeter:
            raise Exception(
                f"Expected {SimDeviceType.SimPowerMeter}, got {component.gt.DeviceType}"
            )
        self.link = link
        link.poll(config.ChannelName for config in component.gt.ConfigList)

    def read_hw_uid(self) -> Result[DriverResult[str | None], Exception]:
        """A simulated meter is the one its layout names."""
        return Ok(DriverResult(self.component.gt.HwUid))

    def read_channel(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        value, error = self.link.latest_value(channel.Name)
        if error is not None:
            return Ok(DriverResult(None, [PlantSilent(error)]))
        return Ok(DriverResult(value))

    def read_power_w(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        return self.read_channel(channel)

    def read_current_rms_micro_amps(
        self, channel: DataChannel
    ) -> Result[DriverResult[int | None], Exception]:
        return self.read_channel(channel)
