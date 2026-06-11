"""Sim-time bridge: listen for the time coordinator's sim.timestep broadcasts.

OFI — this module is deliberately interim. It subscribes to the
MQTT-bridged form of the time coordinator's ``sim.timestep`` broadcast
and parses the JSON by hand, BYPASSING the gwsproto codec on purpose:
a proper named type would build sim-time machinery into the old stack
that the uv/AllyLink rebuild replaces, where timesteps get a typed
path and this module dies. Spec: the ``sim-time`` spoke of the
simulated-test-environment design (wiki/gridworks-scada).

The bridge plan it serves (decided 2026-06-11): the existing scada/LTN
stay on wall clock; the harness runs 1-minute snapshots and 1-minute
timesteps, and each received timestep triggers the link keepalive so
links stay active under harness pacing. The internal watchdogs are
loop-driven and unaffected (verified pat map, sim-time spoke).

Reaching the MQTT side at all requires one broker-side binding the
harness owns: ``timemic_tx -> amq.topic`` (the MQTT plugin's exchange),
which turns the AMQP broadcast key ``rjb.d1-tc.time.sim-timestep``
into the MQTT topic ``rjb/d1-tc/time/sim-timestep``.
"""

import json
import logging
import threading
from typing import Any, Callable, Optional

import paho.mqtt.client as mqtt
from gwproactor.config import MQTTClient

SIM_TIMESTEP_TYPE_NAME = "sim.timestep"
DEFAULT_TIME_COORDINATOR_ALIAS = "d1.tc"

MODULE_LOGGER = logging.getLogger(__name__)


def sim_timestep_mqtt_topic(
    tc_alias: str = DEFAULT_TIME_COORDINATOR_ALIAS,
) -> str:
    """MQTT form of the gwbase broadcast routing key
    ``rjb.<from-alias-dashed>.time.sim-timestep`` (AMQP '.' -> MQTT '/')."""
    return f"rjb/{tc_alias.replace('.', '-')}/time/sim-timestep"


class SimTimeListener:
    """Minimal paho client on its own network thread: tracks the latest
    simulated time and fires ``on_timestep`` for each (monotonic) step.
    Callbacks run on the paho thread — keep them small and thread-safe."""

    def __init__(
        self,
        *,
        config: MQTTClient,
        on_timestep: Optional[Callable[[int], None]] = None,
        tc_alias: str = DEFAULT_TIME_COORDINATOR_ALIAS,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config = config
        self._on_timestep = on_timestep
        self._topic = sim_timestep_mqtt_topic(tc_alias)
        self._logger = logger or MODULE_LOGGER
        self._latest_time_unix_s: Optional[int] = None
        self._lock = threading.Lock()
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        if config.username:
            self._client.username_pw_set(
                config.username, config.password.get_secret_value()
            )
        if config.tls.use_tls:
            # OFI: interim listener is dev-broker-only; TLS rides the rebuild.
            self._logger.warning(
                "SimTimeListener ignores TLS settings (dev-broker-only bridge)"
            )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    @property
    def latest_time_unix_s(self) -> Optional[int]:
        with self._lock:
            return self._latest_time_unix_s

    def start(self) -> None:
        self._client.connect_async(
            self._config.host, self._config.port, keepalive=self._config.keepalive
        )
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def _on_connect(self, client: mqtt.Client, *_args: Any) -> None:
        client.subscribe(self._topic)
        self._logger.info("SimTimeListener subscribed to %s", self._topic)

    def _on_message(
        self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage
    ) -> None:
        self.process_payload(msg.payload)

    def process_payload(self, payload: bytes) -> None:
        """Parse one candidate sim.timestep payload (separated from paho
        for broker-less unit testing)."""
        try:
            d = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._logger.warning("SimTimeListener: undecodable payload ignored")
            return
        if not isinstance(d, dict) or d.get("TypeName") != SIM_TIMESTEP_TYPE_NAME:
            return
        t = d.get("TimeUnixS")
        if not isinstance(t, int):
            self._logger.warning(
                "SimTimeListener: sim.timestep without int TimeUnixS ignored"
            )
            return
        with self._lock:
            # Monotonic guard, mirroring gwbase Orchestrator._handle_timestep:
            # never move simulated time backwards; repeats are re-announced.
            if self._latest_time_unix_s is not None and t < self._latest_time_unix_s:
                return
            self._latest_time_unix_s = t
        if self._on_timestep is not None:
            self._on_timestep(t)
