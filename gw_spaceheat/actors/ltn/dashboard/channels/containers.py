import logging
import time
from enum import auto
from enum import StrEnum
from functools import cached_property
from typing import Any
from typing import Deque
from typing import Optional

from gwsproto.data_classes.hardware_layout import ChannelRegistry
from gwsproto.enums import TelemetryName

from gwsproto.named_types import SnapshotSpaceheat


from actors.ltn.dashboard.channels.channel import HoneywellThermostatStateChannel
from actors.ltn.dashboard.channels.channel import TankChannel
from actors.ltn.dashboard.channels.channel import DEFAULT_MISSING_STRING
from actors.ltn.dashboard.channels.channel import FlowChannel
from actors.ltn.dashboard.channels.channel import MissingReading
from actors.ltn.dashboard.channels.channel import PowerChannel
from actors.ltn.dashboard.channels.channel import PUMP_OFF_THRESHOLD
from actors.ltn.dashboard.channels.channel import PumpPowerChannel
from actors.ltn.dashboard.channels.channel import TemperatureChannel
from actors.ltn.dashboard.channels.read_mixin import UnboundReading
from actors.ltn.dashboard.channels.read_mixin import ReadMixin


def enqueue_fifo_q(element: Any, fifo_q: Deque[Any], max_length: int = 10) -> None:
    """
    Enqueues an element into a FIFO queue represented by a deque object.

    Args:
        element (HackHpStateCapture): The element to be enqueued.
        fifo_q (Deque[HackHpStateCapture]): The FIFO queue represented by a deque object.
        max_length (int, optional): The maximum length of the FIFO queue. Defaults to 10.

    Returns:
        None
    """
    if len(fifo_q) >= max_length:
        fifo_q.pop()  # Remove the oldest element if queue length is equal to max_length
    fifo_q.appendleft(element)  # Add the new element at the beginning

class PumpPowerState(StrEnum):
    NoFlow = auto()
    Flow = auto()

class PumpPowerChannels(ReadMixin):
    primary: PumpPowerChannel
    store: PumpPowerChannel
    dist: PumpPowerChannel
    boiler: PumpPowerChannel
    dist_pump_pwr_state_q: Deque[tuple[PumpPowerState, int, int]]
    dist_pump_pwr_state: PumpPowerState

    def __init__(self, channels: ChannelRegistry) -> None:
        self.primary = PumpPowerChannel("primary-pump-pwr", channels)
        self.store = PumpPowerChannel("store-pump-pwr", channels)
        self.dist = PumpPowerChannel("dist-pump-pwr", channels)
        self.boiler = PumpPowerChannel("oil-boiler-pwr", channels)
        self.dist_pump_pwr_state_q = Deque[tuple[PumpPowerState, int, int]](maxlen=10)
        self.dist_pump_pwr_state = PumpPowerState.NoFlow

    def update(self):
        now = int(time.time())
        if self.dist.reading:
            if self.dist_pump_pwr_state == PumpPowerState.NoFlow:
                if self.dist.reading.converted > PUMP_OFF_THRESHOLD:
                    self.dist_pump_pwr_state = PumpPowerState.Flow
                    tt = [PumpPowerState.Flow, self.dist.reading.converted, now]
                    enqueue_fifo_q(tt, self.dist_pump_pwr_state_q)
            elif self.dist_pump_pwr_state == PumpPowerState.Flow:
                if self.dist.reading.converted < PUMP_OFF_THRESHOLD:
                    self.dist_pump_pwr_state = PumpPowerState.NoFlow
                    tt = [PumpPowerState.NoFlow, self.dist.reading.converted, now]
                    enqueue_fifo_q(tt, self.dist_pump_pwr_state_q)


class PowerChannels(ReadMixin):
    hp_indoor: PowerChannel
    hp_outdoor: PowerChannel
    pumps: PumpPowerChannels

    def __init__(self, channels: ChannelRegistry) -> None:

        self.hp_indoor = PowerChannel("hp-idu-pwr", channels)
        print("hp-idu-pwr type:", type(self.hp_indoor))
        print("hp-idu-pwr repr:", self.hp_indoor)
        print("hp-idu-pwr TelemetryName:", getattr(self.hp_indoor, "TelemetryName", "NO_ATTR"))
        print("hp-idu-pwr telemetry_name:", getattr(self.hp_indoor, "telemetry_name", "NO_ATTR"))
        self.hp_outdoor = PowerChannel("hp-odu-pwr", channels)
        self.hp_total = MissingReading()
        self.pumps = PumpPowerChannels(channels)

class Thermostat(ReadMixin):
    name: str
    set_point: TemperatureChannel
    temperature: TemperatureChannel

    def __init__(
        self, name: str,
        channels: ChannelRegistry,
        *,
        missing_string: str = DEFAULT_MISSING_STRING,
        raise_errors: bool = False,
        logger: Optional[logging.Logger | logging.LoggerAdapter] = None
    ) -> None:
        self.name = name
        self.set_point = TemperatureChannel(
            self.name + "-set",
            channels,
            missing_string=missing_string,
            raise_errors=raise_errors,
            logger=logger
        )
        self.temperature = TemperatureChannel(
            self.name + "-temp",
            channels,
            missing_string = missing_string,
            raise_errors = raise_errors,
            logger = logger,
            )

class HoneywellThermostat(Thermostat):
    state: HoneywellThermostatStateChannel

    def __init__(
        self, name:
        str, channels: ChannelRegistry,
        *,
        fahrenheit_display: bool = True,
        missing_string: str = DEFAULT_MISSING_STRING,
        raise_errors: bool = False,
        logger: Optional[logging.Logger | logging.LoggerAdapter] = None

    ) -> None:
        super().__init__(
            name,
            channels,
            missing_string=missing_string,
            raise_errors=raise_errors,
            logger=logger,
        )
        self.state = HoneywellThermostatStateChannel(
            self.name + "-state",
            channels,
            missing_string=missing_string,
            raise_errors=raise_errors,
            logger=logger,
        )

class Tank(ReadMixin):
    name: str
    depth1: TankChannel
    depth2: TankChannel
    depth3: TankChannel
    depth4: TankChannel
    is_buffer: bool

    def __init__(self, tank_name: str, channels: ChannelRegistry, *, is_buffer: bool = False) -> None:
        self.name = tank_name
        self.depth1 = TankChannel(self.name + "-depth1", channels)
        self.depth2 = TankChannel(self.name + "-depth2", channels)
        self.depth3 = TankChannel(self.name + "-depth3", channels)
        self.depth4 = TankChannel(self.name + "-depth4", channels)
        self.is_buffer = is_buffer

    @cached_property
    def depths(self) -> list[TemperatureChannel]:
        return [self.depth1, self.depth2, self.depth3, self.depth4]

class Tanks(ReadMixin):
    buffer: Tank
    store: list[Tank]

    def __init__(self, num_tanks: int, channels: ChannelRegistry) -> None:
        self.buffer = Tank("buffer", channels, is_buffer=True)
        self.store = [
            Tank(f"tank{tank_idx}", channels)
            for tank_idx in range(1, num_tanks + 1)
        ]

class Temperatures(ReadMixin):
    tanks: Tanks
    thermostats: list[HoneywellThermostat]
    dist_swt: TemperatureChannel   # = "dist-swt"
    dist_rwt: TemperatureChannel   # = "dist-rwt"
    hp_lwt: TemperatureChannel   # = "hp-lwt"
    hp_ewt: TemperatureChannel   # = "hp-ewt"
    buffer_hot_pipe: TemperatureChannel   # = "buffer-hot-pipe"
    buffer_cold_pipe: TemperatureChannel   # = "buffer-cold-pipe"
    store_hot_pipe: TemperatureChannel   # = "store-hot-pipe"
    store_cold_pipe: TemperatureChannel   # = "store-cold-pipe"
    oat: TemperatureChannel   # = "oat"

    def __init__(
        self,
        num_tanks: int,
        thermostat_names: list[str],
        channels: ChannelRegistry
    ) -> None:
        self.tanks = Tanks(num_tanks, channels)
        self.thermostats = [
            HoneywellThermostat(
                f"zone{i+1}-{thermostat_name}", channels
            ) for i, thermostat_name in enumerate(thermostat_names)
        ]
        self.dist_swt = TemperatureChannel("dist-swt", channels)
        self.dist_rwt = TemperatureChannel("dist-rwt", channels)
        self.hp_lwt = TemperatureChannel("hp-lwt", channels)
        self.hp_ewt = TemperatureChannel("hp-ewt", channels)
        self.buffer_hot_pipe = TemperatureChannel("buffer-hot-pipe", channels)
        self.buffer_cold_pipe = TemperatureChannel("buffer-cold-pipe", channels)
        self.store_hot_pipe = TemperatureChannel("store-hot-pipe", channels)
        self.store_cold_pipe = TemperatureChannel("store-cold-pipe", channels)
        self.oat = TemperatureChannel("oat", channels)

class FlowChannels(ReadMixin):
    dist_flow: FlowChannel
    primary_flow: FlowChannel
    store_flow: FlowChannel
    sieg_flow: FlowChannel

    def __init__(self, channels: ChannelRegistry) -> None:
        self.dist_flow = FlowChannel("dist-flow", channels)
        self.primary_flow = FlowChannel("primary-flow", channels)
        self.store_flow = FlowChannel("store-flow", channels)
        self.sieg_flow = FlowChannel("sieg-flow", channels)
        

class Channels(ReadMixin):

    def __init__(
        self,
        channels: ChannelRegistry,
        thermostat_names: list[str],
    ) -> None:
        self._registry = channels
        self.power = PowerChannels(channels)
        self.temperatures = Temperatures(num_tanks=3, thermostat_names=thermostat_names, channels=channels)
        self.flows = FlowChannels(channels)
        self.last_unbound_readings: list[UnboundReading] = []

    def read_snapshot(self, snap: SnapshotSpaceheat) -> list[UnboundReading]:
        self.last_unbound_readings = super().read_snapshot(snap)
        return self.last_unbound_readings
