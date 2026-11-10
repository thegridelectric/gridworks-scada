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
from typing import Callable, Iterable, NamedTuple, Optional

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


class RelayDrive(ABC):
    """One relay, as its actor reaches it. A drive does one thing when
    asked and says how it went: verifying, retrying and reporting a glitch
    are the actor's."""

    @abstractmethod
    async def set(self, action: ChangeRelayPin) -> Optional[str]:
        """Put the relay in this position. None when it took, otherwise
        why it did not."""

    @abstractmethod
    async def read(self) -> Optional[ChangeRelayPin]:
        """The position the relay holds, None when that cannot be told."""


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
