"""Actor-level tests: the relay i2c choreography against the sim register
backend — the GRI-11 failure catalog in code (POR boot-adopt, warm-takeover
latched holds, confirmed actuation, transient-EIO heal via the held command,
permanent-EIO glitch-per-streak, mid-run reset detect/repair/re-assert, and
the garbled-read false-positive guard).

The pinned test layout has no i2c relays; the fixture appends the bus node,
one relay on i2c.relay.component.gt (Zone1Failsafe: expander 0x20, output
register 2, bit 0), and its state channel in-memory before boot. Message
routing between the two actors is wired directly (bus replies feed
relay.process_message), so the futures-based bus ops resolve synchronously.
"""

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest

from actors.i2c_bus import ExpanderReinitialized, I2cBus
from actors.relay import I2cCommand, Relay, UNKNOWN_STATE
from drivers import tca9555
from gwsproto.enums import ChangeRelayPin, LogLevel
from gwsproto.named_types import (
    FsmFullReport,
    Glitch,
    I2cResult,
    SingleMachineState,
)
from gwproto.message import Message
from scada_app import ScadaApp

BUS_NAME = "i2c-bus"
RELAY_NAME = "test-failsafe-relay"
EXPANDER = 0x20  # Zone1Failsafe: expander 1 -> 0x20, output reg 2, bit 0


@pytest.fixture
def app(tmp_path: Path) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.is_simulated = True
    layout = json.loads(Path(settings.paths.hardware_layout).read_text())
    board_id = next(
        c["ComponentId"]
        for c in layout["OtherComponents"]
        if c["TypeName"] == "scada.board.component.gt"
    )
    component_id = str(uuid.uuid4())
    layout["ShNodes"] += [
        {
            "Name": BUS_NAME,
            "ActorClass": "I2cBus",
            "ActorHierarchyName": f"s.{BUS_NAME}",
            "ShNodeId": str(uuid.uuid4()),
            "TypeName": "spaceheat.node.gt",
            "Version": "303",
        },
        {
            "Name": RELAY_NAME,
            "ActorClass": "Relay",
            "ActorHierarchyName": f"s.{RELAY_NAME}",
            "Handle": f"auto.{RELAY_NAME}",
            "ComponentId": component_id,
            "ShNodeId": str(uuid.uuid4()),
            "TypeName": "spaceheat.node.gt",
            "Version": "303",
        },
    ]
    layout["OtherComponents"].append(
        {
            "TypeName": "i2c.relay.component.gt",
            "Version": "000",
            "ComponentId": component_id,
            "BoardComponentId": board_id,
            "RelayName": "Zone1Failsafe",
            "ConfigList": [
                {
                    "TypeName": "relay.control.config",
                    "Version": "000",
                    "ChannelName": RELAY_NAME,
                    "ActorName": RELAY_NAME,
                    "WiringConfig": "DoubleThrow",
                    "EventType": "change.zone.call.source",
                    "DeEnergizingEvent": "SwitchToWallThermostat",
                    "EnergizingEvent": "SwitchToScada",
                    "StateType": "zone.call.source",
                    "DeEnergizedState": "WallThermostat",
                    "EnergizedState": "Scada",
                    "CapturePeriodS": 300,
                    "AsyncCapture": True,
                    "AsyncCaptureDelta": 1,
                }
            ],
        }
    )
    vdc_channel = next(
        c for c in layout["DataChannels"] if c["Name"] == "vdc-relay"
    )
    relay_channel = dict(vdc_channel)
    relay_channel.update(
        Name=RELAY_NAME,
        DisplayName="Test Failsafe Relay",
        AboutNodeName=RELAY_NAME,
        CapturedByNodeName=RELAY_NAME,
        Id=str(uuid.uuid4()),
    )
    layout["DataChannels"].append(relay_channel)
    path = tmp_path / "layout-with-i2c-relay.json"
    path.write_text(json.dumps(layout))
    settings.paths.hardware_layout = path
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


@pytest.fixture
def rig(app: ScadaApp) -> tuple[Relay, I2cBus]:
    bus = I2cBus(BUS_NAME, app)
    relay = Relay(RELAY_NAME, app)
    bus.sent = []
    relay.sent = []

    def relay_send(dst, payload, src=None):
        if dst.name == BUS_NAME:
            bus.process_message(
                Message(Src=RELAY_NAME, Dst=BUS_NAME, Payload=payload)
            )
        else:
            relay.sent.append((dst.name, payload))

    def bus_send(dst, payload, src=None):
        if (
            isinstance(payload, (I2cResult, ExpanderReinitialized))
            and dst.name == RELAY_NAME
        ):
            relay.process_message(
                Message(Src=BUS_NAME, Dst=RELAY_NAME, Payload=payload)
            )
        else:
            bus.sent.append((dst.name, payload))

    relay._send_to = relay_send
    bus._send_to = bus_send
    return relay, bus


def command(relay: Relay, *, energize: bool) -> I2cCommand:
    cfg = relay.relay_actor_config
    return I2cCommand(
        pin_value=1 if energize else 0,
        target_state=cfg.EnergizedState if energize else cfg.DeEnergizedState,
        event_name=cfg.EnergizingEvent if energize else cfg.DeEnergizingEvent,
        relay_pin_event=(
            ChangeRelayPin.Energize if energize else ChangeRelayPin.DeEnergize
        ),
        trigger_id=str(uuid.uuid4()),
        boss=relay.primary_scada,
        send_time_ms=int(time.time() * 1000),
    )


def pin(bus: I2cBus) -> int:
    return bus.i2c.expanders[EXPANDER].read(tca9555.INPUT_PORT_0) & 1


def glitches(actor, summary: str) -> list[Glitch]:
    return [
        p
        for _, p in actor.sent
        if isinstance(p, Glitch) and p.Summary == summary
    ]


def full_reports(relay: Relay) -> list[FsmFullReport]:
    return [p for _, p in relay.sent if isinstance(p, FsmFullReport)]


def state_reports(relay: Relay) -> list[SingleMachineState]:
    return [p for _, p in relay.sent if isinstance(p, SingleMachineState)]


async def boot(relay: Relay, bus: I2cBus) -> None:
    await bus._init_expanders()
    await relay._boot_adopt()


@pytest.mark.asyncio
async def test_por_boot_adopts_deenergized(rig) -> None:
    relay, bus = rig
    assert relay.state == UNKNOWN_STATE
    await boot(relay, bus)
    assert relay.state == "WallThermostat"
    assert state_reports(relay)[-1].State == "WallThermostat"


@pytest.mark.asyncio
async def test_warm_takeover_inherits_latched_hold(rig) -> None:
    relay, bus = rig
    expander = bus.i2c.expanders[EXPANDER]
    expander.write(tca9555.CONFIG_PORT_0, 0x00)
    expander.write(tca9555.CONFIG_PORT_1, 0x00)
    expander.write(tca9555.OUTPUT_PORT_0, 0b0000_0001)  # the hold, latched
    other = bus.i2c.expanders[0x21]
    other.write(tca9555.CONFIG_PORT_0, 0x00)
    other.write(tca9555.CONFIG_PORT_1, 0x00)
    other.write(tca9555.OUTPUT_PORT_0, 0x00)
    other.write(tca9555.OUTPUT_PORT_1, 0x00)
    await boot(relay, bus)
    # warm takeover: the guard left the outputs driving, adoption inherited
    assert expander.read(tca9555.OUTPUT_PORT_0) == 0b0000_0001
    assert relay.state == "Scada"


@pytest.mark.asyncio
async def test_actuation_confirms_then_reports(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert relay.state == "Scada"
    assert pin(bus) == 1
    assert relay._i2c_command is None
    reports = full_reports(relay)
    assert len(reports) == 1
    assert reports[0].TriggerId == cmd.trigger_id
    assert not glitches(relay, "i2c-relay-actuation-failed")


@pytest.mark.asyncio
async def test_transient_eio_heals_on_verify_pass(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    relay.sent.clear()
    cmd = command(relay, energize=True)
    bus.i2c.inject_fault(EXPANDER, count=1)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert relay.state == "WallThermostat"  # no commit
    assert relay._i2c_command is cmd  # held as enforcement target
    assert len(glitches(relay, "i2c-relay-actuation-failed")) == 1
    await relay._verify_and_report()  # the ≤5-min heal
    assert relay.state == "Scada"
    assert pin(bus) == 1
    assert relay._i2c_command is None
    assert len(full_reports(relay)) == 1  # the late report


@pytest.mark.asyncio
async def test_permanent_eio_glitches_once_per_streak(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    relay.sent.clear()
    cmd = command(relay, energize=True)
    bus.i2c.inject_fault(EXPANDER, count=None)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    await relay._verify_and_report()
    await relay._verify_and_report()
    criticals = [
        p
        for _, p in relay.sent
        if isinstance(p, Glitch) and p.Type == LogLevel.Critical
    ]
    assert len(criticals) == 1  # one per failure streak, not per pass
    assert relay.state == "WallThermostat"


@pytest.mark.asyncio
async def test_reset_detected_repaired_reasserted(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert pin(bus) == 1
    bus.sent.clear()
    relay.sent.clear()

    bus.i2c.power_on_reset(EXPANDER)  # the OPS-452 mid-run reset
    await bus._check_expanders()
    assert len(glitches(bus, "i2c-expander-reset")) == 1
    expander = bus.i2c.expanders[EXPANDER]
    assert expander.read(tca9555.CONFIG_PORT_0) == 0x00  # re-initialized
    assert pin(bus) == 0  # safe-off: the relay dropped

    await relay._verify_and_report()  # enforcement re-asserts
    assert pin(bus) == 1
    assert relay.state == "Scada"
    assert len(glitches(relay, "i2c-relay-drift")) == 1


@pytest.mark.asyncio
async def test_reset_repair_pokes_immediate_reassert(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert pin(bus) == 1
    relay.sent.clear()

    bus.i2c.power_on_reset(EXPANDER)
    await bus._check_expanders()  # detect + repair + poke
    await asyncio.sleep(0.1)  # the poked re-assert task runs
    assert pin(bus) == 1  # restored with NO manual verify call
    assert relay.state == "Scada"
    assert len(glitches(relay, "i2c-relay-drift")) == 1


@pytest.mark.asyncio
async def test_garbled_read_does_not_false_positive(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)

    # relay side: a garbled pin read is confirmed by the re-read
    bus.i2c.inject_read_garble(EXPANDER, count=1)
    assert await relay._read_pin_confirmed(1) == 1

    # bus side: a garbled config read must not fire a reset repair
    bus.sent.clear()
    bus.i2c.inject_read_garble(EXPANDER, count=1)
    await bus._check_expanders()
    assert not glitches(bus, "i2c-expander-reset")
    assert pin(bus) == 1  # nothing was re-initialized
