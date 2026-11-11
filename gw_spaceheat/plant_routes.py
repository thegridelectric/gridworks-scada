"""What stands behind each device node of a layout, chosen once where the
app is built: the plant link for a simulated device, the hardware itself
for any other.

A board device's place on its board is resolved from the board's record
either way, so a layout that misplaces a device fails the boot whether or
not its board is simulated.
"""

from typing import Optional

from gwsproto.data_classes.components import (
    GpioRelayComponent,
    GpioSensorComponent,
    I2cDacOutputComponent,
    I2cRelayComponent,
    I2cThermistorReaderComponent,
)
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass
from gwsproto.property_format import SpaceheatName

from dac_drives import I2cDacDrive, KeptLevelDrive, resolve_dac_output
from pin_inputs import GpioPinInput, resolve_gpio_input_pin
from plant import Device, Plant
from plant_link import LinkPinInput, LinkThermistorInput, PlantLink
from relay_drives import (
    GpioRelayDrive,
    I2cRelayDrive,
    resolve_gpio_pin,
    resolve_i2c_actuation,
)
from thermistor_inputs import Ads1115ThermistorInput, resolve_thermistor_adc


def captured_channel_names(layout: HydronicLayout, node_name: str) -> list[SpaceheatName]:
    return [dc.Name for dc in layout.data_channels.values() if dc.CapturedByNodeName == node_name]


def route_devices(plant: Plant, layout: HydronicLayout, link: Optional[PlantLink]) -> None:
    for node in layout.nodes.values():
        device = device_behind(layout, node, link)
        if device is not None:
            plant.route(node.name, device)


def device_behind(
    layout: HydronicLayout, node: ShNode, link: Optional[PlantLink]
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
    return None
