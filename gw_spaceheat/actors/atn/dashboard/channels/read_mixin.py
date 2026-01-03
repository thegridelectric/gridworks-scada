from functools import cached_property
from typing import Any
from typing import Mapping
from typing import Optional
from typing import Sequence

from gwsproto.enums import TelemetryName
from gwsproto.named_types import SingleReading
from gwsproto.named_types import SnapshotSpaceheat

from actors.atn.dashboard.channels.channel import DisplayChannel


class UnusedReading(SingleReading):
    Telemetry: TelemetryName

class ReadMixin:
    def read_snapshot(self, snap: SnapshotSpaceheat, channel_telemetries: dict[str, TelemetryName]) -> list[UnusedReading]:
        """Read all existing child channels, update any ReadMixin children,
        return indices of any readings in the snapshot not read by a configured
        channel.

        This function itself is not meant to be called recursively.
        """
        for channel in self.channels:
            channel.read_snapshot(snap)
        self.update()
        return self.collect_unused_readings(snap, channel_telemetries)

    def collect_unused_readings(
        self,
        snap: SnapshotSpaceheat,
        channel_telemetries: dict[str, TelemetryName]
    ) -> list[UnusedReading]:
        used_indices = {channel.reading.idx for channel in self.channels if channel.reading}
        unused_readings = []
        for reading_idx in range(len(snap.LatestReadingList)):
            if reading_idx not in used_indices:
                unused_reading = snap.LatestReadingList[reading_idx]
                unused_readings.append(
                    UnusedReading(
                        ChannelName=unused_reading.ChannelName,
                        Value=unused_reading.Value,
                        ScadaReadTimeUnixMs=unused_reading.ScadaReadTimeUnixMs,
                        Telemetry=channel_telemetries.get(unused_reading.ChannelName)
                    )
                )
        return unused_readings

    def update_self(self) -> None:
        """Overide with any extra code that must be called after ReadSnapshot"""

    def update_children(self) -> None:
        children = []
        for member in self.__dict__.values():
            if isinstance(member, ReadMixin):
                children.append(member)
            elif isinstance(member, Mapping) and member:
                for submember in member.values():
                    if isinstance(submember, ReadMixin):
                        children.append(submember)
            elif isinstance(member, (tuple, list)) and member:
                for submember in member:
                    if isinstance(submember, ReadMixin):
                        children.append(submember)
        for child in children:
            child.update()

    def update(self):
        self.update_self()
        self.update_children()

    def collect_channels(self, members: Optional[Sequence[Any]] = None) -> list[DisplayChannel]:
        collected_channels = []
        if members is None:
            members = self.__dict__.values()
        for member in members:
            if isinstance(member, DisplayChannel):
                collected_channels.append(member)
            elif isinstance(member, ReadMixin):
                collected_channels.extend(member.collect_channels())
            elif isinstance(member, Mapping) and member:
                collected_channels.extend(self.collect_channels(list(member.values())))
            elif isinstance(member, (tuple, list)) and member:
                collected_channels.extend(self.collect_channels(member))
        return collected_channels

    @cached_property
    def channels(self) -> list[DisplayChannel]:
        return self.collect_channels()
