"""The scada's one clock. The timestep clock's listener is exercised
broker-less through its payload seam; the manual clock is the test seam
every clocked actor runs on."""

import asyncio
import json
from pathlib import Path

import pytest
from gwproactor.config import MQTTClient

from clock import (
    ClockSource,
    ManualClock,
    TimestepClock,
    WallClock,
    build_clock,
    sim_timestep_mqtt_topic,
)
from scada_app import ScadaApp

CONFIG = Path(__file__).parent / "config"


def make_clock(seen: list) -> TimestepClock:
    return TimestepClock(config=MQTTClient(), on_step=seen.append)


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
    clock = make_clock(seen)
    with pytest.raises(RuntimeError, match="before the first"):
        clock.now()
    clock.process_payload(timestep_payload(1_700_000_000))
    clock.process_payload(timestep_payload(1_700_000_060))
    assert seen == [1_700_000_000, 1_700_000_060]
    assert clock.now() == 1_700_000_060
    assert clock.now_ms() == 1_700_000_060_000


def test_monotonic_guard_drops_backwards_steps() -> None:
    seen: list = []
    clock = make_clock(seen)
    clock.process_payload(timestep_payload(1_700_000_060))
    clock.process_payload(timestep_payload(1_700_000_000))  # backwards
    assert seen == [1_700_000_060]
    assert clock.now() == 1_700_000_060
    # A repeat (equal time) is re-announced, mirroring gwbase.
    clock.process_payload(timestep_payload(1_700_000_060))
    assert seen == [1_700_000_060, 1_700_000_060]


def test_garbage_and_foreign_types_ignored() -> None:
    seen: list = []
    clock = make_clock(seen)
    clock.process_payload(b"not json at all")
    clock.process_payload(json.dumps({"TypeName": "heartbeat.a"}).encode())
    clock.process_payload(json.dumps({"TypeName": "sim.timestep", "TimeUnixS": "soon"}).encode())
    assert seen == []
    assert clock.latest_time_unix_s is None


def test_timestep_sleep_wakes_on_the_step_that_reaches_the_target() -> None:
    clock = make_clock([])
    clock.process_payload(timestep_payload(1_700_000_000))
    woke: list[float] = []

    async def run() -> None:
        sleeper = asyncio.create_task(clock.sleep(90))
        await asyncio.sleep(0)
        clock.process_payload(timestep_payload(1_700_000_060))
        await asyncio.sleep(0)
        assert not sleeper.done()
        clock.process_payload(timestep_payload(1_700_000_120))
        await sleeper
        woke.append(clock.now())

    asyncio.run(run())
    assert woke == [1_700_000_120]


def test_manual_clock_holds_still_and_moves_only_on_advance() -> None:
    clock = ManualClock(start_s=1_700_000_000)
    assert clock.now() == 1_700_000_000
    assert clock.now_ms() == 1_700_000_000_000
    clock.advance(30)
    assert clock.now() == 1_700_000_030


def test_manual_clock_sleep_returns_when_advanced_past_the_target() -> None:
    clock = ManualClock(start_s=1_700_000_000)
    order: list[str] = []

    async def sleeper(label: str, seconds: float) -> None:
        await clock.sleep(seconds)
        order.append(label)

    async def run() -> None:
        long = asyncio.create_task(sleeper("long", 100))
        short = asyncio.create_task(sleeper("short", 10))
        await asyncio.sleep(0)
        clock.advance(5)
        await asyncio.sleep(0)
        assert order == []
        clock.advance(5)
        await short
        assert order == ["short"]
        clock.advance(90)
        await long

    asyncio.run(run())
    assert order == ["short", "long"]


def test_wall_clock_tracks_time() -> None:
    import time

    clock = WallClock()
    assert abs(clock.now() - time.time()) < 1


def test_build_clock_refuses_timestep_on_a_real_plant() -> None:
    assert isinstance(build_clock(ClockSource.Wall, False, MQTTClient()), WallClock)
    assert isinstance(build_clock(ClockSource.Timestep, True, MQTTClient()), TimestepClock)
    with pytest.raises(ValueError, match="simulated"):
        build_clock(ClockSource.Timestep, False, MQTTClient())


@pytest.mark.parametrize("pair", ["gw.house0.orange", "gw.nolan"])
def test_app_hands_actors_the_injected_clock(pair: str) -> None:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / f"{pair}.layout.json"
    settings.paths.operational_params = CONFIG / f"{pair}.operational.params.json"
    settings.paths.mkdirs()
    clock = ManualClock(start_s=1_700_000_000)
    app = ScadaApp(app_settings=settings, clock=clock)
    app.instantiate()
    assert app.clock is clock
    assert app.scada.services.clock is clock
    assert app.scada.services.clock.now() == 1_700_000_000


def test_app_defaults_to_the_wall_clock() -> None:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    assert settings.clock_source == ClockSource.Wall
    app = ScadaApp(app_settings=settings)
    assert isinstance(app.clock, WallClock)
