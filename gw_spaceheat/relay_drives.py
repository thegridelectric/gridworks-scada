"""The relays a scada board carries, as their actors drive them: a bit on
an i2c expander, reached through the bus actor, and a native GPIO pin.

Everything a relay's place on the board comes to lives here: the expander's
address and registers, the pin, the level that energizes. The relay's actor
holds none of it.
"""

import asyncio
import uuid
from typing import Any, NamedTuple, Optional

from gwsproto.data_classes.components import GpioRelayComponent, I2cRelayComponent
from gwsproto.data_classes.components.component import BoardResidentComponent
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass, ChangeRelayPin, I2cExpanderType
from gwsproto.named_types import (
    I2cBitAddress,
    I2cReadBit,
    I2cReadReg,
    I2cRegAddress,
    I2cResult,
    I2cWriteBit,
)
from gwsproto.property_format import NonNegativeInt

from actors.i2c_bus import ExpanderCheckRequested, ExpanderReinitialized
from drivers import tca9555
from plant import Heard, Plant, RelayDrive, RelayRead, Send


class I2cActuation(NamedTuple):
    """Physical actuation facts for one board-resident i2c relay, resolved
    once from the board record and component: where the bit lives (bus
    node, chip address, output/input/config registers, bit index), which
    expander chip protocol drives it, the pin level that energizes the
    relay, and whether the board supports pin readback (confirmed vs
    commanded-belief semantics). On a PCF8575 the "registers" are the two
    bytes of its one port word, so input and output coincide and there is
    no config register. Field types mirror i2c.bit.address."""

    bus_node: ShNode
    i2c_address: NonNegativeInt
    expander_type: I2cExpanderType
    output_register: NonNegativeInt
    input_register: NonNegativeInt
    config_register: NonNegativeInt | None
    bit_index: NonNegativeInt
    energized_level: NonNegativeInt
    supports_readback: bool


def resolve_i2c_actuation(layout: HydronicLayout, node: ShNode) -> I2cActuation:
    """RelayName resolved against the component's board record — the
    record's I2cRelays map holds the physical position (expander, output
    register, bit) and the board component holds any field-chosen
    expander address; the layout never restates either."""
    component = node.component
    assert isinstance(component, I2cRelayComponent)
    board = component.board_component
    record = board.device_type
    relay_name = component.gt.RelayName
    capability = next(
        (r for r in record.I2cRelays if r.RelayName == relay_name), None
    )
    if capability is None:
        raise ValueError(
            f"{node.name}: board record {record.DeviceType} has no "
            f"I2cRelays entry named {relay_name}"
        )
    expander = next(
        (e for e in record.Expanders if e.ExpanderIdx == capability.ExpanderIdx),
        None,
    )
    if expander is None:
        raise ValueError(
            f"{node.name}: board record {record.DeviceType} has no "
            f"expander with ExpanderIdx {capability.ExpanderIdx}"
        )
    bus_nodes = [
        n for n in layout.nodes.values() if n.ActorClass == ActorClass.I2cBus
    ]
    if len(bus_nodes) != 1:
        raise ValueError(
            f"{node.name}: expected exactly one I2cBus node in the "
            f"layout; found {len(bus_nodes)}"
        )
    if expander.ExpanderType == I2cExpanderType.Tca9555:
        input_register = tca9555.input_register(capability.RegisterIndex)
        config_register: int | None = tca9555.config_register(
            capability.RegisterIndex
        )
    else:
        input_register = capability.RegisterIndex
        config_register = None
    return I2cActuation(
        bus_node=bus_nodes[0],
        i2c_address=board.expander_address(expander),
        expander_type=expander.ExpanderType,
        output_register=capability.RegisterIndex,
        input_register=input_register,
        config_register=config_register,
        bit_index=capability.BitIndex,
        energized_level=record.RelayEnergizedLevel,
        supports_readback=record.SupportsPinReadback,
    )


def resolve_gpio_pin(layout: HydronicLayout, node: ShNode) -> int:
    """GpioName resolved against the NativeGpioOutputs of the layout's
    board device-type records — the board record carries the physical
    BCM pin."""
    component = node.component
    assert isinstance(component, GpioRelayComponent)
    gpio_name = component.gt.GpioName
    for record in layout.device_types.values():
        for pin in getattr(record, "NativeGpioOutputs", []):
            if pin.Name == gpio_name:
                return pin.BcmPin
    raise ValueError(
        f"{node.name}: no board device-type record in the layout carries "
        f"a native GPIO output named {gpio_name}"
    )


class I2cRelayDrive(RelayDrive):
    """A relay on an expander bit. Every operation is a message to the bus
    actor sent as the relay's node, and the bus actor's reply comes back to
    the relay's actor, which hands it down through hears()."""

    BUS_OP_TIMEOUT_S = 1.0

    def __init__(self, at: I2cActuation) -> None:
        self.at = at
        self.send: Optional[Send] = None
        self.pending_results: dict[str, "asyncio.Future[I2cResult]"] = {}

    @property
    def reads_back(self) -> bool:
        return self.at.supports_readback

    def attach(self, send: Send) -> None:
        self.send = send

    def hears(self, payload: Any) -> Heard:
        if isinstance(payload, I2cResult):
            future = self.pending_results.pop(payload.TriggerId, None)
            if future is not None and not future.done():
                future.set_result(payload)
            # a late reply after timeout is dropped; the timeout already
            # glitched
            return Heard.Taken
        if isinstance(payload, ExpanderReinitialized):
            # The bus actor tells every i2c relay; only the ones on the
            # repaired expander lost their position.
            if payload.I2cAddress == self.at.i2c_address:
                return Heard.Repaired
            return Heard.Taken
        return Heard.NotMine

    def level(self, action: ChangeRelayPin) -> int:
        """The expander pin level for a position: the board's energizing
        level, inverted on an active-low board."""
        pin_value = 1 if action == ChangeRelayPin.Energize else 0
        return pin_value if self.at.energized_level == 1 else 1 - pin_value

    def position(self, level: int) -> ChangeRelayPin:
        if level == self.at.energized_level:
            return ChangeRelayPin.Energize
        return ChangeRelayPin.DeEnergize

    async def bus_op(
        self, payload: I2cWriteBit | I2cReadBit | I2cReadReg
    ) -> I2cResult | None:
        """Send one op to the bus actor and await its I2cResult (None on
        timeout)."""
        assert self.send is not None
        future: "asyncio.Future[I2cResult]" = (
            asyncio.get_running_loop().create_future()
        )
        self.pending_results[payload.TriggerId] = future
        self.send(self.at.bus_node, payload)
        try:
            return await asyncio.wait_for(future, timeout=self.BUS_OP_TIMEOUT_S)
        except asyncio.TimeoutError:
            self.pending_results.pop(payload.TriggerId, None)
            return None

    async def read_bit(self, register: int) -> RelayRead:
        a = self.at
        result = await self.bus_op(
            I2cReadBit(
                Bus=a.bus_node.name,
                Address=I2cBitAddress(
                    I2cAddress=a.i2c_address,
                    RegisterIndex=register,
                    BitIndex=a.bit_index,
                ),
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None:
            return RelayRead(None, "bus op timeout")
        if not result.Success or result.Value is None:
            return RelayRead(None, result.Error or "bus op failed")
        return RelayRead(self.position(result.Value), None)

    async def set(self, action: ChangeRelayPin) -> Optional[str]:
        a = self.at
        result = await self.bus_op(
            I2cWriteBit(
                Bus=a.bus_node.name,
                Address=I2cBitAddress(
                    I2cAddress=a.i2c_address,
                    RegisterIndex=a.output_register,
                    BitIndex=a.bit_index,
                ),
                Value=self.level(action),
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None:
            return "bus op timeout"
        if not result.Success:
            return result.Error or "bus op failed"
        return None

    async def read(self) -> RelayRead:
        """The actual level at the relay's pin, via the expander's
        input-port register."""
        return await self.read_bit(self.at.input_register)

    async def told(self) -> Optional[ChangeRelayPin]:
        """The commanded flip-flop bit (output register): the 07-16 tell
        was output bits reading 1 forty minutes after being set 0."""
        return (await self.read_bit(self.at.output_register)).position

    async def evidence(self) -> str:
        """Snapshot the expander's output and config registers for the port —
        the diagnostic pair that separates a stuck pin (output right, input
        wrong) from the reset signature (config back in input mode). A
        register-less expander has only its port byte to show."""
        a = self.at
        readings = []
        registers = [("output", a.output_register)]
        if a.config_register is not None:
            registers.append(("config", a.config_register))
        for label, register in registers:
            result = await self.bus_op(
                I2cReadReg(
                    Bus=a.bus_node.name,
                    Address=I2cRegAddress(
                        I2cAddress=a.i2c_address, RegisterIndex=register
                    ),
                    NumBytes=1,
                    TriggerId=str(uuid.uuid4()),
                )
            )
            if result is None or not result.Success or result.Value is None:
                readings.append(f"{label}[{register}]=unreadable")
            else:
                readings.append(f"{label}[{register}]=0x{result.Value:02x}")
        return " ".join(readings)

    def check(self) -> None:
        """Ask the bus actor to check this relay's expander for a reset
        now; a reset found there comes back as ExpanderReinitialized."""
        assert self.send is not None
        self.send(
            self.at.bus_node, ExpanderCheckRequested(I2cAddress=self.at.i2c_address)
        )


class GpioRelayDrive(RelayDrive):
    """A relay on a native GPIO output. The pin is written and never read."""

    def __init__(self, bcm_pin: int) -> None:
        self.bcm_pin = bcm_pin
        self.gpio: Any = None

    @property
    def reads_back(self) -> bool:
        return False

    def attach(self, send: Send) -> None:
        import RPi.GPIO as GPIO

        self.gpio = GPIO
        self.gpio.setmode(GPIO.BCM)
        self.gpio.setup(self.bcm_pin, GPIO.OUT)

    async def set(self, action: ChangeRelayPin) -> Optional[str]:
        if action == ChangeRelayPin.Energize:
            self.gpio.output(self.bcm_pin, self.gpio.HIGH)
        else:
            self.gpio.output(self.bcm_pin, self.gpio.LOW)
        return None

    async def read(self) -> RelayRead:
        return RelayRead(None, "a GPIO relay's pin is not read")


def route_board_relays(plant: Plant, layout: HydronicLayout) -> None:
    """Put the board behind every relay on a board that is not simulated."""
    for node in layout.nodes.values():
        component = node.component
        if (
            node.actor_class != ActorClass.Relay
            or not isinstance(component, BoardResidentComponent)
            or component.board_component.simulated
        ):
            continue
        if isinstance(component, I2cRelayComponent):
            plant.route_relay(
                node.name, I2cRelayDrive(resolve_i2c_actuation(layout, node))
            )
        elif isinstance(component, GpioRelayComponent):
            plant.route_relay(node.name, GpioRelayDrive(resolve_gpio_pin(layout, node)))
