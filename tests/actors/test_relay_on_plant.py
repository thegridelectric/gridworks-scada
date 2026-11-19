"""A simulated house's relay actor runs the choreography of the real one
with the plant in place of the board: a command reaches the plant as the
relay's position, the verify pass restates it, and the relay boots as its
board would, adopting a position where the board reads its pins and
knowing none where it does not. Nothing goes to the bus actor."""

import time
import uuid
from pathlib import Path

import pytest
from gwsproto.enums import ChangeRelayPin
from gwsproto.named_types import FsmFullReport, Glitch, SingleMachineState

from actors.relay import UNKNOWN_STATE, I2cCommand, Relay
from plant_link import InProcessPlantLink, PlantLinkKind
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
ENERGIZE = ChangeRelayPin.Energize
DE_ENERGIZE = ChangeRelayPin.DeEnergize


def rig(pair: str, relay_name: str) -> tuple[Relay, InProcessPlantLink]:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / f"{pair}.layout.json"
    settings.paths.operational_params = CONFIG / f"{pair}.operational.params.json"
    settings.plant_link = PlantLinkKind.InProcess
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    link = app.plant_link
    assert isinstance(link, InProcessPlantLink)
    relay = Relay(relay_name, app)
    relay.sent = []
    relay._send_to = lambda dst, payload, src=None: relay.sent.append((dst.name, payload))
    return relay, link


def command(relay: Relay, *, energize: bool) -> I2cCommand:
    cfg = relay.relay_actor_config
    return I2cCommand(
        pin_value=1 if energize else 0,
        target_state=cfg.EnergizedState if energize else cfg.DeEnergizedState,
        event_name=cfg.EnergizingEvent if energize else cfg.DeEnergizingEvent,
        relay_pin_event=ENERGIZE if energize else DE_ENERGIZE,
        trigger_id=str(uuid.uuid4()),
        boss=relay.primary_scada,
        send_time_ms=int(time.time() * 1000),
    )


async def attempt(relay: Relay, *, energize: bool) -> I2cCommand:
    cmd = command(relay, energize=energize)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    return cmd


def sent(relay: Relay, kind: type) -> list:
    return [p for _, p in relay.sent if isinstance(p, kind)]


@pytest.mark.asyncio
async def test_a_relay_on_a_board_that_reads_no_pin_knows_no_position_until_commanded() -> None:
    relay, link = rig("gw.house0.no.sieg.hazel", "store-pump-relay")
    cfg = relay.relay_actor_config

    await relay._boot_adopt()
    assert relay.state == UNKNOWN_STATE
    assert not sent(relay, SingleMachineState)
    assert link.actuations == []

    cmd = await attempt(relay, energize=True)
    assert link.actuations == [("store-pump-relay", ENERGIZE)]
    assert relay.state == cfg.EnergizedState
    assert [r.TriggerId for r in sent(relay, FsmFullReport)] == [cmd.trigger_id]

    await attempt(relay, energize=False)
    assert link.actuations[-1] == ("store-pump-relay", DE_ENERGIZE)
    assert relay.state == cfg.DeEnergizedState
    assert not sent(relay, Glitch)


@pytest.mark.asyncio
async def test_a_relay_on_a_board_that_reads_its_pins_adopts_de_energized_at_boot() -> None:
    relay, link = rig("gw.nolan", "secondary-pump-relay")
    cfg = relay.relay_actor_config

    await relay._boot_adopt()
    assert relay.state == cfg.DeEnergizedState
    assert sent(relay, SingleMachineState)[-1].State == cfg.DeEnergizedState
    assert link.actuations == []

    await attempt(relay, energize=True)
    assert link.actuations == [("secondary-pump-relay", ENERGIZE)]
    assert relay.state == cfg.EnergizedState
    assert not sent(relay, Glitch)


@pytest.mark.asyncio
async def test_the_verify_pass_restates_the_position_to_the_plant() -> None:
    """A plant that missed the command, or restarted since, learns the
    position on the relay's next pass with no new command."""
    relay, link = rig("gw.nolan", "secondary-pump-relay")
    await relay._boot_adopt()
    await attempt(relay, energize=True)

    await relay._verify_and_report()

    assert link.actuations == [("secondary-pump-relay", ENERGIZE)] * 2
    assert not sent(relay, Glitch)


@pytest.mark.asyncio
async def test_a_simulated_relay_sends_nothing_to_the_bus() -> None:
    relay, _link = rig("gw.nolan", "secondary-pump-relay")
    await relay._boot_adopt()
    await attempt(relay, energize=True)
    await relay._verify_and_report()

    bus = next(n.name for n in relay.layout.nodes.values() if n.ActorClass == "I2cBus")
    assert bus not in {dst for dst, _ in relay.sent}


@pytest.mark.asyncio
async def test_a_plant_that_cannot_be_told_is_a_failed_actuation_that_heals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The link raising is the relay's failed write: the same glitch, the
    command held, and the next pass through the plant commits it."""
    relay, link = rig("gw.house0.no.sieg.hazel", "store-pump-relay")
    relay.RETRY_BACKOFF_S = ()
    cfg = relay.relay_actor_config
    await relay._boot_adopt()

    def no_plant_time(_relay_name: str, _action: ChangeRelayPin) -> None:
        raise RuntimeError("no time before the first sim.timestep")

    with monkeypatch.context() as m:
        m.setattr(link, "actuate", no_plant_time)
        cmd = await attempt(relay, energize=True)

    [glitch] = sent(relay, Glitch)
    assert glitch.Summary == "i2c-relay-actuation-failed"
    assert "write failed: telling the plant raised" in glitch.Details
    assert "no time before the first sim.timestep" in glitch.Details
    assert relay.state == UNKNOWN_STATE
    assert relay._i2c_command is cmd
    assert not sent(relay, FsmFullReport)

    await relay._verify_and_report()

    assert link.actuations == [("store-pump-relay", ENERGIZE)]
    assert relay.state == cfg.EnergizedState
    assert [r.TriggerId for r in sent(relay, FsmFullReport)] == [cmd.trigger_id]
