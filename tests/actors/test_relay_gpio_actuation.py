"""A GPIO relay actuates as a task off the proactor's loop, like an I2C
relay. What the task meets after the command arrives is the scada's to
hear about: a write the drive refuses, and a step after the write that
raises, each become one Critical glitch and no report."""

import asyncio
import time
import uuid
from pathlib import Path

import pytest
from gwsproto.enums import ChangeRelayPin, LogLevel
from gwsproto.named_types import FsmEvent, FsmFullReport, Glitch

from actors.relay import Relay
from plant_link import PlantLinkKind
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
BOSS_HANDLE = "auto.five-v-boss.pico-cycler"


def gpio_relay() -> Relay:
    """Nolan's vdc-relay, the one GPIO relay in the fixtures, on the
    simulated board so its device is the in-process plant link."""
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.plant_link = PlantLinkKind.InProcess
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    relay = Relay("vdc-relay", app)
    relay.sent = []
    relay._send_to = lambda dst, payload, src=None: relay.sent.append((dst.name, payload))
    return relay


def energize(relay: Relay) -> FsmEvent:
    return FsmEvent(
        FromHandle=BOSS_HANDLE,
        ToHandle=relay.node.handle,
        EventType=relay.my_event_enum.enum_name(),
        EventName=relay.relay_actor_config.EnergizingEvent,
        TriggerId=str(uuid.uuid4()),
        SendTimeUnixMs=int(time.time() * 1000),
    )


async def actuate(relay: Relay, event: FsmEvent) -> None:
    relay._actuate_and_report(orig_state=relay.state, message=event)
    for _ in range(3):
        await asyncio.sleep(0)


def sent(relay: Relay, kind: type) -> list:
    return [p for _, p in relay.sent if isinstance(p, kind)]


@pytest.mark.asyncio
async def test_a_write_the_drive_refuses_is_one_critical_glitch_and_no_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = gpio_relay()

    async def refused(_action: ChangeRelayPin) -> str:
        return "GPIO 22 write raised RuntimeError('not set up as an OUTPUT')"

    monkeypatch.setattr(relay.drive, "set", refused)
    event = energize(relay)

    await actuate(relay, event)

    [glitch] = sent(relay, Glitch)
    assert glitch.Summary == "relay-actuation-failed"
    assert glitch.Type == LogLevel.Critical
    assert "not set up as an OUTPUT" in glitch.Details
    assert not sent(relay, FsmFullReport)


@pytest.mark.asyncio
async def test_a_step_that_raises_after_the_write_is_one_critical_glitch_and_no_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The write went through, so the pin is where the boss asked; what
    failed is the relay's word about it. The task has nobody above it to
    catch the exception, so the relay says so itself."""
    relay = gpio_relay()

    def broken_state_report(now_ms=None) -> None:
        raise RuntimeError("state channel vanished")

    monkeypatch.setattr(relay, "send_state", broken_state_report)
    event = energize(relay)

    await actuate(relay, event)

    [glitch] = sent(relay, Glitch)
    assert glitch.Summary == "relay-report-failed"
    assert glitch.Type == LogLevel.Critical
    assert event.TriggerId in glitch.Details
    assert "state channel vanished" in glitch.Details
    assert not sent(relay, FsmFullReport)
