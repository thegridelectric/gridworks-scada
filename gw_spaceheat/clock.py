"""The scada's one clock: wall time, the time coordinator's timesteps, or a
value a test moves. Actors reach it through ``services.clock`` and never
keep a copy; every plant-time read and wait goes through it, while IO
durations stay on the wall.

The coordinator's ``sim.timestep`` broadcast reaches the scada in its
MQTT-bridged form and is parsed by hand here, bypassing the codec: a
proper named type would build sim-time machinery into the stack the
AllyLink rebuild replaces, where timesteps get a typed path. Reaching the
MQTT side at all needs one broker-side binding the harness owns,
``timemic_tx -> amq.topic``, which turns the AMQP routing key
``rjb.d1-tc.time.sim-timestep`` into the topic ``rjb/d1-tc/time/sim-timestep``.
"""

import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, tzinfo
from enum import auto
from typing import Any, Callable, Optional

import paho.mqtt.client as mqtt
from gwproactor.config import MQTTClient
from gwsproto.enums.gw_str_enum import GwStrEnum
from gwsproto.property_format import UTCMilliseconds

SIM_TIMESTEP_TYPE_NAME = "sim.timestep"
DEFAULT_TIME_COORDINATOR_ALIAS = "d1.tc"

MODULE_LOGGER = logging.getLogger(__name__)


class ClockSource(GwStrEnum):
    """The settings value that picks the clock. Manual is not a settings
    value: a test injects it in code, so no env file can put a box on it."""

    Wall = auto()
    Timestep = auto()


class Clock(ABC):
    @abstractmethod
    def now(self) -> float:
        """Plant time as unix seconds, the drop-in for time.time()."""

    def now_ms(self) -> UTCMilliseconds:
        return int(self.now() * 1000)

    def local_now(self, tz: tzinfo) -> datetime:
        return datetime.fromtimestamp(self.now(), tz)

    @abstractmethod
    async def sleep(self, seconds: float) -> None:
        """Return once plant time has advanced by seconds."""


class WallClock(Clock):
    def now(self) -> float:
        return time.time()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class Sleepers:
    """The waits pending on a stepped clock: each a target time and the
    future that resolves once the clock reaches it. Wakes are handed to
    the sleeper's own loop, so a step arriving on another thread is safe."""

    def __init__(self) -> None:
        self.pending: list[tuple[float, asyncio.AbstractEventLoop, asyncio.Future[None]]] = []
        self.lock = threading.Lock()

    async def wait_until(self, target: float, now: float) -> None:
        if now >= target:
            await asyncio.sleep(0)
            return
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        with self.lock:
            self.pending.append((target, loop, fut))
        await fut

    def wake(self, now: float) -> None:
        with self.lock:
            due = [p for p in self.pending if p[0] <= now]
            self.pending = [p for p in self.pending if p[0] > now]
        for _, loop, fut in due:
            loop.call_soon_threadsafe(self.resolve, fut)

    @staticmethod
    def resolve(fut: asyncio.Future[None]) -> None:
        if not fut.done():
            fut.set_result(None)


class ManualClock(Clock):
    """A stored value the test moves with advance(); never touches wall time."""

    def __init__(self, start_s: float) -> None:
        self.time_s = start_s
        self.sleepers = Sleepers()

    def now(self) -> float:
        return self.time_s

    def advance(self, seconds: float) -> None:
        self.time_s += seconds
        self.sleepers.wake(self.time_s)

    async def sleep(self, seconds: float) -> None:
        await self.sleepers.wait_until(self.time_s + seconds, self.time_s)


def sim_timestep_mqtt_topic(tc_alias: str = DEFAULT_TIME_COORDINATOR_ALIAS) -> str:
    """MQTT form of the gwbase broadcast routing key
    rjb.<from-alias-dashed>.time.sim-timestep (AMQP '.' -> MQTT '/')."""
    return f"rjb/{tc_alias.replace('.', '-')}/time/sim-timestep"


class TimestepClock(Clock):
    """now() is the latest coordinator step and holds until the next; sleep()
    waits until a step reaches its target. No interpolation with wall time
    between steps, and now() before the first step raises. The paho client
    on its own network thread is the transport; on_step runs on that thread
    for each monotonic step, so it stays small and thread-safe."""

    def __init__(
        self,
        *,
        config: MQTTClient,
        on_step: Optional[Callable[[int], None]] = None,
        tc_alias: str = DEFAULT_TIME_COORDINATOR_ALIAS,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config = config
        self.on_step = on_step
        self.topic = sim_timestep_mqtt_topic(tc_alias)
        self.logger = logger or MODULE_LOGGER
        self.latest_time_unix_s: Optional[int] = None
        self.lock = threading.Lock()
        self.sleepers = Sleepers()
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        if config.username:
            self.client.username_pw_set(config.username, config.password.get_secret_value())
        if config.tls.use_tls:
            self.logger.warning("TimestepClock ignores TLS settings (dev-broker-only bridge)")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def now(self) -> float:
        with self.lock:
            t = self.latest_time_unix_s
        if t is None:
            raise RuntimeError("TimestepClock has no time before the first sim.timestep")
        return float(t)

    async def sleep(self, seconds: float) -> None:
        now = self.now()
        await self.sleepers.wait_until(now + seconds, now)

    def start(self) -> None:
        self.client.connect_async(self.config.host, self.config.port, keepalive=self.config.keepalive)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def on_connect(self, client: mqtt.Client, *_args: Any) -> None:
        client.subscribe(self.topic)
        self.logger.info("TimestepClock subscribed to %s", self.topic)

    def on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        self.process_payload(msg.payload)

    def process_payload(self, payload: bytes) -> None:
        """Take one candidate sim.timestep payload (separated from paho for
        broker-less unit testing)."""
        try:
            d = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.logger.warning("TimestepClock: undecodable payload ignored")
            return
        if not isinstance(d, dict) or d.get("TypeName") != SIM_TIMESTEP_TYPE_NAME:
            return
        t = d.get("TimeUnixS")
        if not isinstance(t, int):
            self.logger.warning("TimestepClock: sim.timestep without int TimeUnixS ignored")
            return
        with self.lock:
            # Monotonic guard, mirroring gwbase Orchestrator._handle_timestep:
            # never move simulated time backwards; repeats are re-announced.
            if self.latest_time_unix_s is not None and t < self.latest_time_unix_s:
                return
            self.latest_time_unix_s = t
        self.sleepers.wake(float(t))
        if self.on_step is not None:
            self.on_step(t)


def build_clock(source: ClockSource, simulated: bool, mqtt_config: MQTTClient) -> Clock:
    """The clock the settings ask for. Timestep needs a simulated plant: a
    box with real hardware never waits on a coordinator."""
    if source == ClockSource.Wall:
        return WallClock()
    if source == ClockSource.Timestep:
        if not simulated:
            raise ValueError("clock_source Timestep requires a layout with a simulated component")
        return TimestepClock(config=mqtt_config)
    raise ValueError(f"Unknown clock source {source}")
