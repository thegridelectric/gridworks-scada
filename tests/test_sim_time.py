"""Broker-less unit tests for the sim-time bridge listener."""

import json

from gwproactor.config import MQTTClient

from sim_time import SimTimeListener, sim_timestep_mqtt_topic


def make_listener(seen: list) -> SimTimeListener:
    return SimTimeListener(config=MQTTClient(), on_timestep=seen.append)


def timestep_payload(time_unix_s: int) -> bytes:
    return json.dumps(
        {
            "FromGNodeAlias": "d1.tc",
            "FromGNodeInstanceId": "19ee09df-80ba-437b-b6c1-1eebe9d34801",
            "TimeUnixS": time_unix_s,
            "TimestepCreatedMs": time_unix_s * 1000,
            "MessageId": "7499defd-c54a-4061-a37a-17f3c84f88a2",
            "TypeName": "sim.timestep",
            "Version": "000",
        }
    ).encode()


def test_topic_shape() -> None:
    assert sim_timestep_mqtt_topic() == "rjb/d1-tc/time/sim-timestep"
    assert sim_timestep_mqtt_topic("d1.tc.x") == "rjb/d1-tc-x/time/sim-timestep"


def test_timesteps_advance_and_fire() -> None:
    seen: list = []
    listener = make_listener(seen)
    listener.process_payload(timestep_payload(1_700_000_000))
    listener.process_payload(timestep_payload(1_700_000_060))
    assert seen == [1_700_000_000, 1_700_000_060]
    assert listener.latest_time_unix_s == 1_700_000_060


def test_monotonic_guard_drops_backwards_steps() -> None:
    seen: list = []
    listener = make_listener(seen)
    listener.process_payload(timestep_payload(1_700_000_060))
    listener.process_payload(timestep_payload(1_700_000_000))  # backwards
    assert seen == [1_700_000_060]
    assert listener.latest_time_unix_s == 1_700_000_060
    # A repeat (equal time) is re-announced, mirroring gwbase.
    listener.process_payload(timestep_payload(1_700_000_060))
    assert seen == [1_700_000_060, 1_700_000_060]


def test_garbage_and_foreign_types_ignored() -> None:
    seen: list = []
    listener = make_listener(seen)
    listener.process_payload(b"not json at all")
    listener.process_payload(json.dumps({"TypeName": "heartbeat.a"}).encode())
    listener.process_payload(
        json.dumps({"TypeName": "sim.timestep", "TimeUnixS": "soon"}).encode()
    )
    assert seen == []
    assert listener.latest_time_unix_s is None
