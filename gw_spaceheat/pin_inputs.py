"""A native GPIO input of a scada board, as its sensor's actor reads it."""

from typing import Any

from gwsproto.data_classes.components import GpioSensorComponent
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass

from plant import PIN_READ_FAILED, PinInput, PinRead, Plant, Said, Send


def resolve_gpio_input_pin(layout: HydronicLayout, node: ShNode) -> int:
    """GpioName resolved against the NativeGpioInputs of the layout's
    board device-type records — the board record carries the physical
    BCM pin."""
    component = node.component
    assert isinstance(component, GpioSensorComponent)
    gpio_name = component.gt.GpioName
    for record in layout.device_types.values():
        for pin in getattr(record, "NativeGpioInputs", []):
            if pin.Name == gpio_name:
                return pin.BcmPin
    raise ValueError(
        f"{node.name}: no board device-type record in the layout carries "
        f"a native GPIO input named {gpio_name}"
    )


class GpioPinInput(PinInput):
    def __init__(self, bcm_pin: int) -> None:
        self.bcm_pin = bcm_pin
        self.gpio: Any = None

    def attach(self, send: Send) -> None:
        import RPi.GPIO as GPIO

        self.gpio = GPIO
        self.gpio.setmode(GPIO.BCM)
        self.gpio.setup(self.bcm_pin, GPIO.IN)

    def read(self) -> PinRead:
        try:
            raw = self.gpio.input(self.bcm_pin)
        except Exception as e:  # noqa: BLE001
            return PinRead(
                None, (Said(PIN_READ_FAILED, f"GPIO {self.bcm_pin} read raised {e!r}", True),)
            )
        return PinRead(1 if raw else 0, ())


def route_board_pins(plant: Plant, layout: HydronicLayout) -> None:
    """Put the pin behind every GPIO sensor on a board that is not
    simulated."""
    for node in layout.nodes.values():
        component = node.component
        if (
            node.actor_class == ActorClass.GpioSensor
            and isinstance(component, GpioSensorComponent)
            and not component.board_component.simulated
        ):
            plant.route(node.name, GpioPinInput(resolve_gpio_input_pin(layout, node)))
