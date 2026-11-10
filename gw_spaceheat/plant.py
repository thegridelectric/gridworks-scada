"""The house as the scada's device actors reach it.

A device actor asks the plant for its own device by node name: a sensor
asks for the readings of its channels, a relay for something to drive.
What answers is chosen once, where the app is built, and the actor cannot
tell which it has. Channel names and relay positions are all an actor
says to the plant: no address, register or pin.

The plant routes and does nothing else. It holds no device logic, no
retry and no state beyond its routes. An actor that asks for a node
nothing was routed for fails the boot.
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Callable, Iterable, NamedTuple, Optional

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ChangeRelayPin
from gwsproto.property_format import SpaceheatName, UTCMilliseconds


class PlantReadings(NamedTuple):
    """Channel values at one read time, in each channel's own encoding.
    What a sensor source hands a sensor. Interior to the scada and never
    serialised: the sensor's actor makes the ``synced.readings`` from it."""

    channel_names: tuple[SpaceheatName, ...]
    values: tuple[int, ...]
    read_time_ms: UTCMilliseconds


Deliver = Callable[[PlantReadings], None]


class SensorSource(ABC):
    """Where a sensing device's readings come from."""

    @abstractmethod
    def sense(self, channel_names: Iterable[SpaceheatName], deliver: Deliver) -> None:
        """Hand deliver every reading of these channels from now on."""


class RelayRead(NamedTuple):
    """One read of a relay: the position it holds, or None with why the
    read failed. Interior to the scada and never serialised."""

    position: Optional[ChangeRelayPin]
    error: Optional[str]


class Heard(Enum):
    """What a relay drive made of a message its relay's actor was sent."""

    NotMine = auto()
    Taken = auto()
    Repaired = auto()


Send = Callable[[ShNode, Any], None]


class RelayDrive(ABC):
    """One relay, as its actor reaches it. A drive does one thing when
    asked and says how it went: confirming a set, retrying it and reporting
    a glitch are the actor's."""

    @property
    @abstractmethod
    def reads_back(self) -> bool:
        """Whether read() tells what the relay holds. Where it cannot, the
        actor believes what it last set."""

    def attach(self, send: Send) -> None:
        """The relay's actor is built. A drive that reaches its device
        through another actor sends as the relay's node, with send."""

    def hears(self, payload: Any) -> Heard:
        """A message the relay's actor was sent and does not know itself:
        the other half of what the drive sent. Repaired says the device
        lost its position and is ready to be set again."""
        return Heard.NotMine

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


class Plant:
    def __init__(self) -> None:
        self.source_by_node: dict[SpaceheatName, SensorSource] = {}
        self.drive_by_node: dict[SpaceheatName, RelayDrive] = {}

    def route_sensor(self, node_name: SpaceheatName, source: SensorSource) -> None:
        if node_name in self.source_by_node:
            raise ValueError(f"{node_name} already has a sensor source in the plant")
        self.source_by_node[node_name] = source

    def route_relay(self, node_name: SpaceheatName, drive: RelayDrive) -> None:
        if node_name in self.drive_by_node:
            raise ValueError(f"{node_name} already has a relay drive in the plant")
        self.drive_by_node[node_name] = drive

    def sense(
        self,
        node_name: SpaceheatName,
        channel_names: Iterable[SpaceheatName],
        deliver: Deliver,
    ) -> None:
        source = self.source_by_node.get(node_name)
        if source is None:
            raise ValueError(f"{node_name} has no sensor source in the plant")
        source.sense(channel_names, deliver)

    def relay(self, node_name: SpaceheatName) -> RelayDrive:
        drive = self.drive_by_node.get(node_name)
        if drive is None:
            raise ValueError(f"{node_name} has no relay drive in the plant")
        return drive
