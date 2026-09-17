import asyncio
import time
from typing import Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwsproto.data_classes.components import SimSensorComponent
from gwsproto.enums import TelemetryName
from gwsproto.named_types import SyncedReadings
from result import Ok, Result

from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface

DEFAULT_CAPTURE_S = 5

# Plausible standing sim values, keyed by TelemetryName (raw int in the
# telemetry's own scaling). Anything not listed reports 0 (idle), which is a
# safe value for power / flow / relay-style channels.
_SIM_VALUE_BY_TELEMETRY: dict[TelemetryName, int] = {
    TelemetryName.WaterTempCTimes1000: 50_000,   # 50 C
    TelemetryName.WaterTempFTimes1000: 122_000,  # 122 F
    TelemetryName.AirTempCTimes1000: 21_000,     # 21 C
    TelemetryName.AirTempFTimes1000: 70_000,     # 70 F
    TelemetryName.CelsiusTimes100: 5_000,        # 50 C
    TelemetryName.HzTimes100: 6_000,             # 60 Hz
    TelemetryName.GpmTimes100: 400,              # 4 gpm
    TelemetryName.MicroHz: 2_000_000,            # 2 Hz
}


class SimSensorActor(ShNodeActor):
    """A self-generating sim sensor (Sema component `sim.sensor.component.gt`).

    On a timer it emits synthetic `SyncedReadings` for every channel in its
    component `ConfigList`, choosing a standing value by each channel's
    `TelemetryName`. It replaces a pico-fed device actor in a simulated layout so
    the scada's sensor channels populate with no pico and no faked HTTP transport.
    Layout-agnostic: usable for any home's simulated variant.
    """

    _stop_requested: bool

    def __init__(self, name: str, services: ScadaAppInterface) -> None:
        super().__init__(name, services)
        self._stop_requested = False
        self._component = self.node.component
        if not isinstance(self._component, SimSensorComponent):
            raise ValueError(
                f"ERROR. SimSensorActor {name} expects a SimSensorComponent; "
                f"got {type(self._component)}."
            )
        # The channels this sensor reports are those bound to its node via
        # DataChannel.CapturedByNodeName — the sole channel→node binding (per the
        # layout-boundary spoke), so the sim component needs no ConfigList.
        self._channel_names = [
            ch.Name
            for ch in self.layout.data_channels.values()
            if ch.CapturedByNodeName == self.name
        ]
        self._capture_s = DEFAULT_CAPTURE_S
        self.feeds_derived = self.layout.feeds_derived(self._channel_names)

    def _sim_value(self, channel_name: str) -> int:
        channel = self.layout.data_channels.get(channel_name)
        if channel is None:
            return 0
        return _SIM_VALUE_BY_TELEMETRY.get(channel.TelemetryName, 0)

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self._capture_s * 2.1)]

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name=f"{self.name} keepalive")
        )

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop takes care of shutting down the associated task."""

    def readings(self) -> SyncedReadings | None:
        """One post's worth of standing values, None when the sensor captures nothing."""
        names = [c for c in self._channel_names if c in self.layout.data_channels]
        if not names:
            return None
        return SyncedReadings(
            ChannelNameList=names,
            ValueList=[self._sim_value(c) for c in names],
            ScadaReadTimeUnixMs=int(time.time() * 1000),
        )

    def post(self) -> None:
        """Send the standing readings the way a pico-fed device actor does:
        to the scada, and to the derived generator when it consumes them."""
        msg = self.readings()
        if msg is None:
            return
        self._send_to(self.primary_scada, msg)
        if self.feeds_derived:
            self._send_to(self.derived_generator, msg)

    async def main(self) -> None:
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            self.post()
            await asyncio.sleep(self._capture_s)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        return Ok(True)
