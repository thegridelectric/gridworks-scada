"""Actor-level tests: the relay i2c choreography against the sim register
backend — the GRI-11 failure catalog in code (POR boot-adopt, warm-takeover
latched holds, confirmed actuation, transient-EIO heal via the held command,
permanent-EIO glitch-per-streak, mid-run reset detect/repair/re-assert, and
the garbled-read false-positive guard).

The pinned artifact pair is decoded through the sema words (NolanLayout on
the boot assembly path + NolanOperationalParams), and the fixture asserts
the layout rides a gw108 board (nolan layout and gw108 do not always go
together). gw.nolan.layout axiom 3 (LocalControlPlant) forces the plant and
zone-circuit relays to exist, so the rig adopts the first zone circuit's
failsafe relay — nothing synthetic is appended, and the physical address
(expander, registers, bit) is the actor's own board-record resolution.
Message routing between the two actors is wired directly (bus replies feed
relay.process_message), so the futures-based bus ops resolve synchronously.
"""

# OFI: run this same failure catalog against a House0-family layout with a
# simulated Krida (i2c-multiplexer) board once that actuation path is
# restored — the both-cases merge gate wants the legacy path witnessed too.

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest

from actors.i2c_bus import ExpanderReinitialized, I2cBus
from actors.relay import I2cCommand, Relay, UNKNOWN_STATE
from drivers import tca9555
from gwsproto.enums import ChangeRelayPin, DeviceType, LogLevel, ZoneCallSource
from gwsproto.named_types import (
    FsmFullReport,
    Glitch,
    NolanOperationalParams,
    I2cResult,
    NolanLayout,
    ScadaBoardComponentGt,
    SingleMachineState,
)
from gwproto.message import Message
from scada_app import ScadaApp
from sema_to_dc import assemble_runtime_layout


@pytest.fixture
def app() -> tuple[ScadaApp, NolanLayout]:
    settings = ScadaApp.get_settings()
    ops = NolanOperationalParams.model_validate_json(
        Path(settings.paths.operational_params).read_text()
    )
    layout = NolanLayout.model_validate(
        assemble_runtime_layout(
            json.loads(Path(settings.paths.hardware_layout).read_text()),
            ops.model_dump(by_alias=True, exclude_none=True),
        )
    )
    board = next(c for c in layout.Components if isinstance(c, ScadaBoardComponentGt))
    # a nolan layout does not imply a gw108 board; this rig requires both
    assert board.DeviceType == DeviceType.GridworksSimGw108.value
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app, layout


@pytest.fixture
def rig(app: tuple[ScadaApp, NolanLayout]) -> tuple[Relay, I2cBus]:
    scada_app, layout = app
    relay_name = layout.Hydronic.ZoneCallCircuits[0].FailsafeRelayNode
    relay = Relay(relay_name, scada_app)
    bus = I2cBus(relay._i2c.bus_node.name, scada_app)
    bus.sent = []
    relay.sent = []

    def relay_send(dst, payload, src=None):
        if dst.name == bus.name:
            bus.process_message(Message(Src=relay.name, Dst=bus.name, Payload=payload))
        else:
            relay.sent.append((dst.name, payload))

    def bus_send(dst, payload, src=None):
        if (
            isinstance(payload, (I2cResult, ExpanderReinitialized))
            and dst.name == relay.name
        ):
            relay.process_message(
                Message(Src=bus.name, Dst=relay.name, Payload=payload)
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


def pin(relay: Relay, bus: I2cBus) -> int:
    a = relay._i2c
    return (bus.i2c.expanders[a.i2c_address].read(a.input_register) >> a.bit_index) & 1


def glitches(actor, summary: str) -> list[Glitch]:
    return [p for _, p in actor.sent if isinstance(p, Glitch) and p.Summary == summary]


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
    assert relay.state == ZoneCallSource.WallThermostat
    assert state_reports(relay)[-1].State == ZoneCallSource.WallThermostat


@pytest.mark.asyncio
async def test_warm_takeover_inherits_latched_hold(rig) -> None:
    relay, bus = rig
    a = relay._i2c
    expander = bus.i2c.expanders[a.i2c_address]
    expander.write(tca9555.CONFIG_PORT_0, 0x00)
    expander.write(tca9555.CONFIG_PORT_1, 0x00)
    expander.write(a.output_register, 1 << a.bit_index)  # the hold, latched
    for address, other in bus.i2c.expanders.items():
        if address == a.i2c_address:
            continue
        other.write(tca9555.CONFIG_PORT_0, 0x00)
        other.write(tca9555.CONFIG_PORT_1, 0x00)
        other.write(tca9555.OUTPUT_PORT_0, 0x00)
        other.write(tca9555.OUTPUT_PORT_1, 0x00)
    await boot(relay, bus)
    # warm takeover: the guard left the outputs driving, adoption inherited
    assert expander.read(a.output_register) == 1 << a.bit_index
    assert relay.state == ZoneCallSource.Scada


@pytest.mark.asyncio
async def test_actuation_confirms_then_reports(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert relay.state == ZoneCallSource.Scada
    assert pin(relay, bus) == 1
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
    bus.i2c.inject_fault(relay._i2c.i2c_address, count=1)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert relay.state == ZoneCallSource.WallThermostat  # no commit
    assert relay._i2c_command is cmd  # held as enforcement target
    assert len(glitches(relay, "i2c-relay-actuation-failed")) == 1
    await relay._verify_and_report()  # the ≤5-min heal
    assert relay.state == ZoneCallSource.Scada
    assert pin(relay, bus) == 1
    assert relay._i2c_command is None
    assert len(full_reports(relay)) == 1  # the late report


@pytest.mark.asyncio
async def test_permanent_eio_glitches_once_per_streak(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    relay.sent.clear()
    cmd = command(relay, energize=True)
    bus.i2c.inject_fault(relay._i2c.i2c_address, count=None)
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
    assert relay.state == ZoneCallSource.WallThermostat


@pytest.mark.asyncio
async def test_reset_detected_repaired_reasserted(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert pin(relay, bus) == 1
    bus.sent.clear()
    relay.sent.clear()

    bus.i2c.power_on_reset(relay._i2c.i2c_address)  # the OPS-452 mid-run reset
    await bus._check_expanders()
    assert len(glitches(bus, "i2c-expander-reset")) == 1
    expander = bus.i2c.expanders[relay._i2c.i2c_address]
    assert expander.read(tca9555.CONFIG_PORT_0) == 0x00  # re-initialized
    assert pin(relay, bus) == 0  # safe-off: the relay dropped

    await relay._verify_and_report()  # enforcement re-asserts
    assert pin(relay, bus) == 1
    assert relay.state == ZoneCallSource.Scada
    assert len(glitches(relay, "i2c-relay-drift")) == 1


@pytest.mark.asyncio
async def test_reset_repair_pokes_immediate_reassert(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert pin(relay, bus) == 1
    relay.sent.clear()

    bus.i2c.power_on_reset(relay._i2c.i2c_address)
    await bus._check_expanders()  # detect + repair + poke
    await asyncio.sleep(0.1)  # the poked re-assert task runs
    assert pin(relay, bus) == 1  # restored with NO manual verify call
    assert relay.state == ZoneCallSource.Scada
    assert len(glitches(relay, "i2c-relay-drift")) == 1


@pytest.mark.asyncio
async def test_garbled_read_does_not_false_positive(rig) -> None:
    relay, bus = rig
    await boot(relay, bus)
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)

    # relay side: a garbled pin read is confirmed by the re-read
    bus.i2c.inject_read_garble(relay._i2c.i2c_address, count=1)
    assert await relay._read_pin_confirmed(1) == 1

    # bus side: a garbled config read must not fire a reset repair
    bus.sent.clear()
    bus.i2c.inject_read_garble(relay._i2c.i2c_address, count=1)
    await bus._check_expanders()
    assert not glitches(bus, "i2c-expander-reset")
    assert pin(relay, bus) == 1  # nothing was re-initialized
