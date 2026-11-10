"""The scada's end of the connection to a simulated plant.

A layout with a simulated device has no hardware behind it. What its
sensors see arrives from the plant as ``sim.plant.flux``, and each relay
position goes to the plant as ``sim.plant.actuation``. Actors reach the
link through ``services.plant_link`` and speak channel names and relay
node names only: no address, register or pin crosses.

The link is not an actor, has no node in the layout and holds no physics.
A layout with no simulated device builds none.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import auto
from typing import Any, Callable, Iterable, Mapping, NamedTuple, Optional

import paho.mqtt.client as mqtt
from gwproactor.config import MQTTClient
from gwproto import Message
from gwproto.topic import MQTTTopic
from gwsproto.enums import ChangeRelayPin
from gwsproto.enums.gw_str_enum import GwStrEnum
from gwsproto.named_types import SimPlantActuation, SimPlantFlux
from gwsproto.property_format import SpaceheatName, UtcIso8601Millis, UTCMilliseconds
from pydantic import ValidationError

from clock import Clock

# A plant quiet for this long is taken as gone. Its next flux is a fresh
# start, and a plant that has just started knows no relay position.
PLANT_SILENT_AFTER_S = 15.0

MODULE_LOGGER = logging.getLogger(__name__)


class PlantLinkKind(GwStrEnum):
    """The settings value that picks how a simulated layout reaches its plant."""

    Broker = auto()
    InProcess = auto()


class PlantReadings(NamedTuple):
    """Channel values at one plant read time, in each channel's own encoding.
    The link hands a sensor the part of a flux its channels cover. Interior
    to the scada: a slice of ``sim.plant.flux``, never serialised."""

    channel_names: tuple[SpaceheatName, ...]
    values: tuple[int, ...]
    read_time_ms: UTCMilliseconds


Deliver = Callable[[PlantReadings], None]


class PlantLink(ABC):
    def __init__(self, *, silent_after_s: float, monotonic: Callable[[], float]) -> None:
        self.silent_after_s = silent_after_s
        self.monotonic = monotonic
        self.heard_at: Optional[float] = None
        self.sensor_by_channel: dict[str, Deliver] = {}
        self.positions: dict[str, ChangeRelayPin] = {}
        self.unsensed_channels: set[str] = set()

    def start(self) -> None:
        """Open the connection to the plant, where there is one to open."""

    def stop(self) -> None:
        """Close what start() opened."""

    def sense(self, channel_names: Iterable[str], deliver: Deliver) -> None:
        """Route these channels' plant values to deliver. A channel has one
        sensor, as it has one capturing node in the layout."""
        for name in channel_names:
            if name in self.sensor_by_channel:
                raise ValueError(f"channel {name} already has a sensor on the plant link")
            self.sensor_by_channel[name] = deliver

    def set_relay(self, relay_name: str, action: ChangeRelayPin) -> None:
        """Tell the plant a relay's position and keep it. Telling it again
        is how a lost actuation heals."""
        self.positions[relay_name] = action
        self.actuate(relay_name, action)

    def relay(self, relay_name: str) -> Optional[ChangeRelayPin]:
        """What the plant was last told of this relay, None if never told."""
        return self.positions.get(relay_name)

    def restate(self) -> None:
        for relay_name, action in self.positions.items():
            self.actuate(relay_name, action)

    def plant_is_silent(self) -> bool:
        return (
            self.heard_at is None
            or self.monotonic() - self.heard_at > self.silent_after_s
        )

    def take(self, flux: PlantReadings) -> None:
        """One flux from the plant: each sensor gets its own channels, in
        the flux's order. A plant heard after silence is first told every
        relay position."""
        if self.plant_is_silent():
            self.restate()
        self.heard_at = self.monotonic()
        indexes_by_sensor: dict[Deliver, list[int]] = {}
        for i, name in enumerate(flux.channel_names):
            deliver = self.sensor_by_channel.get(name)
            if deliver is None:
                self.note_unsensed(name)
                continue
            indexes_by_sensor.setdefault(deliver, []).append(i)
        for deliver, indexes in indexes_by_sensor.items():
            deliver(
                PlantReadings(
                    channel_names=tuple(flux.channel_names[i] for i in indexes),
                    values=tuple(flux.values[i] for i in indexes),
                    read_time_ms=flux.read_time_ms,
                )
            )

    def note_unsensed(self, channel_name: str) -> None:
        if channel_name not in self.unsensed_channels:
            self.unsensed_channels.add(channel_name)
            MODULE_LOGGER.warning("plant flux carries %s, which no sensor reads", channel_name)

    @abstractmethod
    def actuate(self, relay_name: str, action: ChangeRelayPin) -> None:
        """Send one relay position to the plant."""


class InProcessPlantLink(PlantLink):
    """The plant link with no broker: the test is the plant. It shows the
    scada channel values and reads back what the relays told it."""

    def __init__(self, *, silent_after_s: float, monotonic: Callable[[], float]) -> None:
        super().__init__(silent_after_s=silent_after_s, monotonic=monotonic)
        self.actuations: list[tuple[str, ChangeRelayPin]] = []

    def show(self, values: Mapping[str, int], read_time_ms: UTCMilliseconds) -> None:
        self.take(
            PlantReadings(
                channel_names=tuple(values),
                values=tuple(values.values()),
                read_time_ms=read_time_ms,
            )
        )

    def actuate(self, relay_name: str, action: ChangeRelayPin) -> None:
        self.actuations.append((relay_name, action))


def plant_flux_topic(plant_alias: str, scada_alias: str) -> str:
    return MQTTTopic.encode(
        Message.type_name(), plant_alias, scada_alias, SimPlantFlux.type_name_value()
    )


def wall_time_utc() -> UtcIso8601Millis:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class BrokerPlantLink(PlantLink):
    """The plant link over MQTT, on a client of its own so that losing it
    is a sensor outage and nothing else. Nothing here asks for an
    acknowledgement. The paho network thread only hands work to the
    scada's event loop: sensors and relay positions are touched on that
    loop alone."""

    def __init__(
        self,
        *,
        config: MQTTClient,
        scada_alias: str,
        plant_alias: str,
        clock: Clock,
        silent_after_s: float,
        monotonic: Callable[[], float],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(silent_after_s=silent_after_s, monotonic=monotonic)
        self.config = config
        self.scada_alias = scada_alias
        self.plant_alias = plant_alias
        self.clock = clock
        self.logger = logger or MODULE_LOGGER
        self.flux_topic = plant_flux_topic(plant_alias, scada_alias)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        if config.username:
            self.client.username_pw_set(config.username, config.password.get_secret_value())
        if config.tls.use_tls:
            self.logger.warning("BrokerPlantLink ignores TLS settings (dev-broker-only)")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.client.connect_async(self.config.host, self.config.port, keepalive=self.config.keepalive)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def on_connect(self, client: mqtt.Client, *_args: Any) -> None:
        client.subscribe(self.flux_topic)
        self.logger.info("BrokerPlantLink subscribed to %s", self.flux_topic)
        self.in_loop(self.restate)

    def on_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        self.in_loop(self.take_payload, msg.payload)

    def in_loop(self, callback: Callable[..., None], *args: Any) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(callback, *args)

    def take_payload(self, payload: bytes) -> None:
        """Take one candidate flux payload (separated from paho for
        broker-less unit testing)."""
        try:
            flux = Message[SimPlantFlux].model_validate_json(payload).Payload
        except ValidationError as e:
            self.logger.warning("BrokerPlantLink: payload that is no sim.plant.flux ignored: %s", e)
            return
        self.take(
            PlantReadings(
                channel_names=tuple(flux.ChannelNameList),
                values=tuple(flux.ValueList),
                read_time_ms=flux.ScadaReadTimeUnixMs,
            )
        )

    def actuate(self, relay_name: str, action: ChangeRelayPin) -> None:
        message = Message[SimPlantActuation](
            Src=self.scada_alias,
            Dst=self.plant_alias,
            Payload=SimPlantActuation(
                RelayName=relay_name,
                Action=action,
                ActuationTimeUnixMs=self.clock.now_ms(),
                ActualTimeUtc=wall_time_utc(),
            ),
        )
        self.client.publish(message.mqtt_topic(), message.model_dump_json().encode(), qos=0)


def build_plant_link(
    kind: PlantLinkKind,
    simulated: bool,
    *,
    mqtt_config: MQTTClient,
    scada_alias: str,
    plant_alias: str,
    clock: Clock,
) -> Optional[PlantLink]:
    """The plant link the settings ask for, and none at all for a layout
    with no simulated device."""
    if not simulated:
        return None
    if kind == PlantLinkKind.InProcess:
        return InProcessPlantLink(silent_after_s=PLANT_SILENT_AFTER_S, monotonic=time.monotonic)
    if kind == PlantLinkKind.Broker:
        return BrokerPlantLink(
            config=mqtt_config,
            scada_alias=scada_alias,
            plant_alias=plant_alias,
            clock=clock,
            silent_after_s=PLANT_SILENT_AFTER_S,
            monotonic=time.monotonic,
        )
    raise ValueError(f"Unknown plant link kind {kind}")
