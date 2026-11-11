"""The house as the scada's device actors reach it.

A device actor asks the plant for its own device, by node name and by the
kind of device it drives. What answers is chosen once, where the app is
built, and the actor cannot tell which it has. Channel names, positions and
levels are all an actor says to its device: no address, register or pin.

The plant routes and does nothing else. It holds no device logic, no
retry and no state beyond its routes. An actor that asks for a node
nothing was routed for, or for a kind the node's device is not, fails the
boot.
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Callable, Iterable, NamedTuple, Optional, TypeVar

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ChangeRelayPin
from gwsproto.property_format import SpaceheatName, UTCMilliseconds


Send = Callable[[ShNode, Any], None]


class Heard(Enum):
    """What a device made of a message its actor was sent."""

    NotMine = auto()
    Taken = auto()
    Repaired = auto()


class Device:
    """What stands behind one node, reached by that node's actor alone.

    A device does one thing when asked and says how it went. Nothing it is
    asked to do raises: whatever its hardware throws is caught in the
    device, the one place that knows what its hardware can throw, and
    comes back as the reason. The actor catches nothing and reports every
    reason it is handed."""

    def attach(self, send: Send) -> None:
        """The device's actor is built. A device that reaches its hardware
        through another actor sends as its own actor's node, with send."""

    def hears(self, payload: Any) -> Heard:
        """A message the device's actor was sent and does not know itself:
        the other half of what the device sent. Repaired says the hardware
        lost what it was last set to and is ready to be set again."""
        return Heard.NotMine


DeviceT = TypeVar("DeviceT", bound=Device)


class Said(NamedTuple):
    """Something a device says of itself, for its actor to report as a
    glitch. A streak one is said by every call that fails the same way and
    is reported once, until a call no longer says it."""

    summary: str
    details: str
    streak: bool


class Streaks:
    """Which of the things an actor's device says are new to report."""

    def __init__(self) -> None:
        self.running: dict[str, set[str]] = {}

    def fresh(self, about: str, said: Iterable[Said]) -> list[Said]:
        """What to report of what one call said. about names what was
        asked, so that two channels failing the same way are two streaks."""
        said = list(said)
        running = self.running.get(about, set())
        self.running[about] = {s.summary for s in said if s.streak}
        return [s for s in said if not s.streak or s.summary not in running]


class PlantReadings(NamedTuple):
    """Channel values at one read time, in each channel's own encoding.
    What a sensor source hands a sensor. Interior to the scada and never
    serialised: the sensor's actor makes the ``synced.readings`` from it."""

    channel_names: tuple[SpaceheatName, ...]
    values: tuple[int, ...]
    read_time_ms: UTCMilliseconds


Deliver = Callable[[PlantReadings], None]


class SensorSource(Device, ABC):
    """A sensing device that reports when it has something to report."""

    @abstractmethod
    def sense(self, channel_names: Iterable[SpaceheatName], deliver: Deliver) -> None:
        """Hand deliver every reading of these channels from now on."""


class RelayRead(NamedTuple):
    """One read of a relay: the position it holds, or None with why the
    read failed. Interior to the scada and never serialised."""

    position: Optional[ChangeRelayPin]
    error: Optional[str]


class RelayDrive(Device, ABC):
    """One relay, as its actor reaches it. A drive does one thing when
    asked and says how it went: confirming a set, retrying it and reporting
    a glitch are the actor's."""

    @property
    @abstractmethod
    def reads_back(self) -> bool:
        """Whether read() tells what the relay holds. Where it cannot, the
        actor believes what it last set."""

    @abstractmethod
    async def set(self, action: ChangeRelayPin) -> Optional[str]:
        """Put the relay in this position. None when the device took the
        write, otherwise why it did not."""

    @abstractmethod
    async def read(self) -> RelayRead:
        """The position the relay holds."""

    async def told(self) -> Optional[ChangeRelayPin]:
        """The position the device says it was last told to hold, None
        when it cannot say. It differs from the last set when the device
        has lost it."""
        return None

    async def evidence(self) -> str:
        """What the device shows of itself after a set that did not
        confirm, for the glitch."""
        return ""

    def check(self) -> None:
        """A set did not take: have what the relay sits on check itself."""


PIN_READ_FAILED = "gpio-read-failed"


class PinRead(NamedTuple):
    """One read of an input pin: 0 or 1, or None with what the device said
    of a read that failed. None with nothing said is a pin with nothing to
    read yet."""

    value: Optional[int]
    said: tuple[Said, ...]


class PinInput(Device, ABC):
    """One digital input, read when its actor asks."""

    @abstractmethod
    def read(self) -> PinRead:
        """The pin's level now."""


class Plant:
    def __init__(self) -> None:
        self.device_by_node: dict[SpaceheatName, Device] = {}

    def route(self, node_name: SpaceheatName, device: Device) -> None:
        if node_name in self.device_by_node:
            raise ValueError(f"{node_name} already has a device in the plant")
        self.device_by_node[node_name] = device

    def device(self, node_name: SpaceheatName, kind: type[DeviceT]) -> DeviceT:
        device = self.device_by_node.get(node_name)
        if device is None:
            raise ValueError(f"{node_name} has no device in the plant")
        if not isinstance(device, kind):
            raise ValueError(
                f"{node_name} has a {type(device).__name__} in the plant, "
                f"which is no {kind.__name__}"
            )
        return device
