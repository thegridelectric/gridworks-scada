"""What stands behind each device node of a layout, chosen once where the
app is built: the plant link for a simulated device, the hardware itself
for any other.

A board device's place on its board is resolved from the board's record
either way, so a layout that misplaces a device fails the boot whether or
not its board is simulated.

A pico-fed node has a device here only when it is simulated: a real pico
posts to its node's actor over HTTP, and nothing in the scada asks it.
"""

import logging
import time
from typing import Optional

from gwproactor.config import MQTTClient
from gwsproto.data_classes.components import (
    ElectricMeterComponent,
    GpioRelayComponent,
    GpioSensorComponent,
    I2cDacOutputComponent,
    I2cRelayComponent,
    I2cThermistorReaderComponent,
    SimPicoBtuMeterComponent,
    SimPicoTankModuleComponent,
)
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass, DeviceType, SimDeviceType
from gwsproto.property_format import SpaceheatName

from actors.config import ScadaSettings
from clock import Clock
from dac_drives import I2cDacDrive, KeptLevelDrive, resolve_dac_output
from drivers.power_meter.egauge_4030__power_meter_driver import EGuage4030_PowerMeterDriver
from drivers.power_meter.plant_link__power_meter_driver import PlantLink_PowerMeterDriver
from pin_inputs import GpioPinInput, resolve_gpio_input_pin
from plant import Device, Plant
from plant_link import (
    PLANT_SILENT_AFTER_S,
    BrokerPlantLink,
    InProcessPlantLink,
    LinkPinInput,
    LinkThermistorInput,
    PlantLink,
    PlantLinkKind,
)
from relay_drives import (
    GpioRelayDrive,
    I2cRelayDrive,
    resolve_gpio_pin,
    resolve_i2c_actuation,
)
from standing_plant import StandingPlantLink
from thermistor_inputs import Ads1115ThermistorInput, resolve_thermistor_adc


def captured_channel_names(layout: HydronicLayout, node_name: str) -> list[SpaceheatName]:
    return [dc.Name for dc in layout.data_channels.values() if dc.CapturedByNodeName == node_name]


def build_plant_link(
    kind: PlantLinkKind,
    layout: HydronicLayout,
    *,
    simulated: bool,
    mqtt_config: MQTTClient,
    clock: Clock,
) -> Optional[PlantLink]:
    """The plant link the settings ask for, and none at all for a layout
    with no simulated device."""
    if not simulated:
        return None
    if kind == PlantLinkKind.Standing:
        return StandingPlantLink(
            layout,
            silent_after_s=PLANT_SILENT_AFTER_S,
            monotonic=time.monotonic,
            wall=time.time,
        )
    if kind == PlantLinkKind.InProcess:
        return InProcessPlantLink(silent_after_s=PLANT_SILENT_AFTER_S, monotonic=time.monotonic)
    if kind == PlantLinkKind.Broker:
        return BrokerPlantLink(
            config=mqtt_config,
            scada_alias=layout.scada_g_node_alias,
            plant_alias=layout.terminal_asset_g_node_alias,
            clock=clock,
            silent_after_s=PLANT_SILENT_AFTER_S,
            monotonic=time.monotonic,
        )
    raise ValueError(f"Unknown plant link kind {kind}")


def route_devices(
    plant: Plant, layout: HydronicLayout, link: Optional[PlantLink], settings: ScadaSettings
) -> None:
    for node in layout.nodes.values():
        device = device_behind(layout, node, link, settings)
        if device is not None:
            plant.route(node.name, device)


def device_behind(
    layout: HydronicLayout, node: ShNode, link: Optional[PlantLink], settings: ScadaSettings
) -> Optional[Device]:
    """The device of one node, None for a node that has none."""

    def the_link() -> PlantLink:
        if link is None:
            raise ValueError(f"{node.name} is simulated and the layout has no plant link")
        return link

    component = node.component
    actor_class = node.actor_class
    if actor_class == ActorClass.SimSensorActor:
        return the_link()
    if isinstance(component, (SimPicoTankModuleComponent, SimPicoBtuMeterComponent)):
        return the_link()
    if actor_class == ActorClass.Relay and isinstance(component, I2cRelayComponent):
        actuation = resolve_i2c_actuation(layout, node)
        if component.board_component.simulated:
            return the_link().drive(node.name, reads_back=actuation.supports_readback)
        return I2cRelayDrive(actuation)
    if actor_class == ActorClass.Relay and isinstance(component, GpioRelayComponent):
        bcm_pin = resolve_gpio_pin(layout, node)
        if component.board_component.simulated:
            return the_link().drive(node.name, reads_back=False)
        return GpioRelayDrive(bcm_pin)
    if actor_class == ActorClass.GpioSensor and isinstance(component, GpioSensorComponent):
        bcm_pin = resolve_gpio_input_pin(layout, node)
        if component.board_component.simulated:
            [channel_name] = captured_channel_names(layout, node.name)
            return LinkPinInput(the_link(), channel_name)
        return GpioPinInput(bcm_pin)
    if actor_class == ActorClass.ZeroTenOutputer and isinstance(component, I2cDacOutputComponent):
        output = resolve_dac_output(layout, node)
        if component.board_component.simulated:
            return KeptLevelDrive()
        return I2cDacDrive(output)
    if actor_class == ActorClass.I2cThermistorReader and isinstance(
        component, I2cThermistorReaderComponent
    ):
        adc = resolve_thermistor_adc(layout, node)
        if component.board_component.simulated:
            return LinkThermistorInput(
                the_link(),
                {
                    temp_channel: electrical_cfg.ChannelName
                    for temp_channel, electrical_cfg in adc.channels.electrical_cfg_by_device.items()
                },
            )
        return Ads1115ThermistorInput(adc)
    if actor_class == ActorClass.PowerMeter and isinstance(component, ElectricMeterComponent):
        meter_type = component.device_type.DeviceType
        if meter_type == SimDeviceType.SimPowerMeter:
            return PlantLink_PowerMeterDriver(component, settings, the_link())
        if meter_type == DeviceType.EgaugePowerMeter:
            return EGuage4030_PowerMeterDriver(
                component, settings, logger=logging.getLogger(settings.logging.base_log_name)
            )
        raise NotImplementedError(f"No ElectricMeter driver yet for {meter_type}")
    return None
