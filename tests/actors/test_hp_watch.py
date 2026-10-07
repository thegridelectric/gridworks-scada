"""The heat-pump threshold machine at hp-watch, in-process on the sim
Nolan fixture: Unknown until the first hp-odu power read, HpDetectedOn
above the on line, HpDetectedOff below the off line, held in between, and
Unknown again when the channel flatlines."""

import time
from pathlib import Path

import pytest
from gwproto.message import Header, Message

from actors.hp_boss.sensing import HP_TRAITS
from actors.hp_watch import HELD_ON_S, HP_WATCH_HELD_ON, HpWatch
from actors.in_process_messages import ChannelSubscribe
from gwsproto.enums import LogLevel, SpruceHackHpState
from gwsproto.named_types import ChannelFlatlined, Glitch, SingleMachineState, SingleReading
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
HP_WATCH = "hp-watch"


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def hp_watch_actor(app: ScadaApp) -> HpWatch:
    actor = app.get_communicator_as_type(HP_WATCH, HpWatch)
    assert actor is not None, "hp-watch is constructed in every Nolan layout"
    return actor


def capture(actor: HpWatch) -> list:
    sent: list = []
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def deliver(actor: HpWatch, src: str, payload) -> None:
    actor.process_message(
        Message(
            header=Header(Src=src, Dst=actor.name, MessageType=payload.TypeName),
            Payload=payload,
        )
    )


def power(
    actor: HpWatch, watts: int, channel: str = HCN.hp_odu_pwr, read_s: float | None = None
) -> None:
    """A reading, stamped now unless read_s says when it was read."""
    deliver(
        actor,
        CoreNodeNames.asset_power_meter,
        SingleReading(
            ChannelName=channel,
            Value=watts,
            ScadaReadTimeUnixMs=int((time.time() if read_s is None else read_s) * 1000),
        ),
    )


def held_on_glitches(sent: list) -> list[Glitch]:
    return [p for _, p in sent if isinstance(p, Glitch) and p.Summary == HP_WATCH_HELD_ON]


def flatline(actor: HpWatch, channel: str = HCN.hp_odu_pwr) -> None:
    deliver(
        actor,
        CoreNodeNames.asset_power_meter,
        ChannelFlatlined(
            FromName=CoreNodeNames.asset_power_meter,
            Channel=actor.layout.data_channels[channel],
        ),
    )


def reported_states(sent: list) -> list[str]:
    return [p.State for dst, p in sent if isinstance(p, SingleMachineState)]


def test_start_subscribes_to_hp_odu_power_and_reports_unknown(app: ScadaApp) -> None:
    actor = hp_watch_actor(app)
    sent = capture(actor)
    actor.start()
    assert [(dst, p.ChannelName) for dst, p in sent if isinstance(p, ChannelSubscribe)] == [
        (CoreNodeNames.primary_scada, HCN.hp_odu_pwr)
    ]
    [(dst, state)] = [(dst, p) for dst, p in sent if isinstance(p, SingleMachineState)]
    assert dst == CoreNodeNames.primary_scada
    assert state.MachineHandle == HP_WATCH
    assert state.StateEnum == SpruceHackHpState.enum_name()
    assert state.State == SpruceHackHpState.Unknown


def test_the_machine_crosses_at_each_line_and_holds_in_between(app: ScadaApp) -> None:
    """One report per transition: a read above the on line detects on, a
    read below the off line detects off, and a read on a line or between
    the two changes nothing."""
    actor = hp_watch_actor(app)
    traits = HP_TRAITS[actor.layout.node(HSNN.hp_odu).component.gt.DeviceType]
    sent = capture(actor)

    power(actor, traits.on_above_w + 1)
    assert actor.state == SpruceHackHpState.HpDetectedOn
    power(actor, traits.on_above_w + 900)
    power(actor, traits.on_above_w)
    power(actor, traits.off_below_w)
    assert actor.state == SpruceHackHpState.HpDetectedOn

    power(actor, traits.off_below_w - 1)
    assert actor.state == SpruceHackHpState.HpDetectedOff
    power(actor, 0)
    power(actor, traits.off_below_w)
    power(actor, traits.on_above_w)
    assert actor.state == SpruceHackHpState.HpDetectedOff

    power(actor, traits.on_above_w + 1)
    assert reported_states(sent) == [
        SpruceHackHpState.HpDetectedOn,
        SpruceHackHpState.HpDetectedOff,
        SpruceHackHpState.HpDetectedOn,
    ]


def test_a_read_between_the_lines_while_unknown_detects_off(app: ScadaApp) -> None:
    """The first read leaves Unknown wherever it falls. Between the lines,
    with no earlier state to hold, it is HpDetectedOff: running the pump
    when the system is not hot destratifies the buffer. The same holds
    after a flatline."""
    actor = hp_watch_actor(app)
    traits = HP_TRAITS[actor.layout.node(HSNN.hp_odu).component.gt.DeviceType]
    between = (traits.on_above_w + traits.off_below_w) // 2
    sent = capture(actor)
    assert actor.state == SpruceHackHpState.Unknown

    power(actor, between)
    assert actor.state == SpruceHackHpState.HpDetectedOff

    power(actor, traits.on_above_w + 1)
    flatline(actor)
    power(actor, between)
    assert reported_states(sent) == [
        SpruceHackHpState.HpDetectedOff,
        SpruceHackHpState.HpDetectedOn,
        SpruceHackHpState.Unknown,
        SpruceHackHpState.HpDetectedOff,
    ]


def test_a_flatline_goes_unknown_and_a_fresh_read_comes_back(app: ScadaApp) -> None:
    actor = hp_watch_actor(app)
    traits = HP_TRAITS[actor.layout.node(HSNN.hp_odu).component.gt.DeviceType]
    sent = capture(actor)
    power(actor, traits.on_above_w + 1)

    flatline(actor)
    assert actor.state == SpruceHackHpState.Unknown
    flatline(actor)
    power(actor, traits.on_above_w + 1)
    assert reported_states(sent) == [
        SpruceHackHpState.HpDetectedOn,
        SpruceHackHpState.Unknown,
        SpruceHackHpState.HpDetectedOn,
    ]


def test_other_channels_do_not_move_the_machine(app: ScadaApp) -> None:
    actor = hp_watch_actor(app)
    traits = HP_TRAITS[actor.layout.node(HSNN.hp_odu).component.gt.DeviceType]
    sent = capture(actor)
    power(actor, traits.on_above_w + 1)

    power(actor, 0, channel="primary-pump-pwr")
    flatline(actor, channel="primary-pump-pwr")
    assert actor.state == SpruceHackHpState.HpDetectedOn
    assert reported_states(sent) == [SpruceHackHpState.HpDetectedOn]


def test_held_on_between_the_lines_for_the_hold_warns_once_per_spell(app: ScadaApp) -> None:
    """HpDetectedOn with every read between the lines for HELD_ON_S is a
    stopped unit whose standby draw is above the off line: the pump is
    running between cycles. One Warning glitch per such spell, the state
    unchanged; a read above the on line starts a new spell."""
    actor = hp_watch_actor(app)
    traits = HP_TRAITS[actor.layout.node(HSNN.hp_odu).component.gt.DeviceType]
    between = traits.off_below_w + 5
    sent = capture(actor)
    t0 = 1_800_000_000.0
    power(actor, traits.on_above_w + 1, read_s=t0)

    # The spell runs from the first between-read, 10 s after the On read.
    for elapsed in (10, 60, 300, 10 + HELD_ON_S - 1):
        power(actor, between, read_s=t0 + elapsed)
    assert held_on_glitches(sent) == []

    power(actor, between, read_s=t0 + 10 + HELD_ON_S)
    [glitch] = held_on_glitches(sent)
    assert glitch.Type == LogLevel.Warning
    assert glitch.Node == HP_WATCH
    assert f"{between} W" in glitch.Details
    assert actor.state == SpruceHackHpState.HpDetectedOn

    power(actor, between, read_s=t0 + 2 * HELD_ON_S)
    assert len(held_on_glitches(sent)) == 1

    power(actor, traits.on_above_w + 1, read_s=t0 + 3 * HELD_ON_S)
    for elapsed in (10, 10 + HELD_ON_S):
        power(actor, between, read_s=t0 + 3 * HELD_ON_S + elapsed)
    assert len(held_on_glitches(sent)) == 2


def test_a_stop_inside_the_hold_warns_nothing(app: ScadaApp) -> None:
    """The wind-down after a stop passes between the lines and reaches the
    off line within the hold, so a normal stop raises nothing, and a
    between-read while HpDetectedOff is an idle pulse, not a held On."""
    actor = hp_watch_actor(app)
    traits = HP_TRAITS[actor.layout.node(HSNN.hp_odu).component.gt.DeviceType]
    between = (traits.on_above_w + traits.off_below_w) // 2
    sent = capture(actor)
    t0 = 1_800_000_000.0
    power(actor, traits.on_above_w + 1, read_s=t0)
    power(actor, between, read_s=t0 + 30)
    power(actor, traits.off_below_w - 1, read_s=t0 + 60)
    for elapsed in (120, 600 + HELD_ON_S):
        power(actor, between, read_s=t0 + elapsed)
    assert held_on_glitches(sent) == []
    assert actor.state == SpruceHackHpState.HpDetectedOff
