import asyncio
from typing import Sequence

from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwsproto.data_classes.components import SimSensorComponent
from gwsproto.named_types import SyncedReadings
from result import Ok, Result

from actors.sh_node_actor import ShNodeActor
from plant import PlantReadings
from scada_app_interface import ScadaAppInterface

KEEPALIVE_S = 5


class SimSensorActor(ShNodeActor):
    """A sensor fed by the simulated plant (Sema component
    `sim.sensor.component.gt`).

    It reports what the plant says its channels read, when the plant says
    it, and nothing otherwise: a silent plant is a sensor that has stopped
    reporting. It stands where a pico-fed device actor stands in a real
    layout, for any home's simulated variant.
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
        self._channel_names = self.layout.enabled_channel_names(
            ch.Name
            for ch in self.layout.data_channels.values()
            if ch.CapturedByNodeName == self.name
        )
        if self.layout.node_disabled(self.name):
            self._channel_names = []
        self.feeds_derived = self.layout.feeds_derived(self._channel_names)
        self.services.plant.sense(self.name, self._channel_names, self.take)

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, KEEPALIVE_S * 2.1)]

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name=f"{self.name} keepalive")
        )

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop takes care of shutting down the associated task."""

    def take(self, readings: PlantReadings) -> None:
        """Send what the plant read the way a pico-fed device actor sends a
        post: to the scada, and to the derived generator when it consumes
        them."""
        msg = SyncedReadings(
            ChannelNameList=list(readings.channel_names),
            ValueList=list(readings.values),
            ScadaReadTimeUnixMs=readings.read_time_ms,
        )
        self._send_to(self.primary_scada, msg)
        if self.feeds_derived:
            self._send_to(self.derived_generator, msg)

    async def main(self) -> None:
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            await asyncio.sleep(KEEPALIVE_S)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        return Ok(True)
