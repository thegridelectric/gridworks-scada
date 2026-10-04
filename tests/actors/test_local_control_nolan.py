"""NolanBufferOnlyCoolingTou: layout-family selection, the top machine, and TOU
cooling — the schedule at its boundaries, the state-command sequencing
(ON: iso valve OpenValve → pump CloseRelay → hp-boss TurnOn; OFF: hp-boss
TurnOff → pump OpenRelay), the zone holds (SwitchToScada + ops OpenRelay on circuit
positions 1/2/4), and the two prevention layers: gw.nolan.layout axiom 3
rejects a plant-incomplete layout at decode, and construction crashes —
never degrades — if the contract is somehow bypassed.

Selection/top-machine tests ride the pinned Nolan fixture; TOU tests ride
the frozen spruce artifact."""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import pytest
import pytz

from actors.local_control.nolan.buffer_only_cooling_tou import NolanBufferOnlyCoolingTou
from actors.hp_boss.sensing import HP_TRAITS
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control_loader import LocalControl
from gwsproto.enums import (
    ChangeRelayState,
    ChangeValveState,
    ChangeZoneCallSource,
    LocalControlTopEvent,
    LocalControlTopState,
    NolanLcBufferOnlyState,
    SeasonalStorageMode,
    ServiceMode,
    TurnHpOnOff,
)
from gwsproto.named_types import (
    FsmEvent,
    OperationalParams,
    NolanLayout,
    SingleMachineState,
)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatChannelNames as HCN,
)
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)
from gwsproto.names.nolan.node_names import NolanNodeNames
from scada_app import ScadaApp
from sema_to_dc import assemble_runtime_layout

LC_NAME = CoreNodeNames.local_control
SPRUCE_LAYOUT = Path(__file__).parent.parent / "config" / "gw.nolan.layout.json"
SPRUCE_OPS = (
    Path(__file__).parent.parent
    / "config"
    / "gw.nolan.operational.params.json"
)
ET = pytz.timezone("America/New_York")


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def make_impl(app: ScadaApp) -> NolanBufferOnlyCoolingTou:
    lc = LocalControl(LC_NAME, app)
    assert isinstance(lc._impl, NolanBufferOnlyCoolingTou)
    inner = lc._impl
    inner.sent = []
    inner._send_to = lambda dst, payload, src=None: inner.sent.append(
        (dst.name, payload)
    )
    return inner


@pytest.fixture
def impl(app: ScadaApp) -> NolanBufferOnlyCoolingTou:
    return make_impl(app)


@pytest.fixture
def spruce_impl(tmp_path: Path) -> NolanBufferOnlyCoolingTou:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    settings.paths.operational_params = SPRUCE_OPS
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return make_impl(scada_app)


def test_nolan_layout_selects_nolan_local_control(impl: NolanBufferOnlyCoolingTou) -> None:
    assert impl.top_state == LocalControlTopState.Normal


@pytest.mark.parametrize("service", [ServiceMode.Cooling, ServiceMode.Heating])
def test_nolan_all_tanks_selects_no_machine(
    tmp_path: Path, service: ServiceMode
) -> None:
    """A Nolan layout has a machine only for BufferOnly; AllTanks in either
    service mode raises at selection."""
    ops = json.loads(SPRUCE_OPS.read_text())
    ops["ServiceMode"] = service.value
    ops["FamilyParams"]["SeasonalStorageMode"] = SeasonalStorageMode.AllTanks.value
    path = tmp_path / "gw.nolan.operational.params.json"
    path.write_text(json.dumps(ops))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    settings.paths.operational_params = path
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    with pytest.raises(Exception, match="No local control machine"):
        scada_app.instantiate()


def test_top_machine_round_trip(impl: NolanBufferOnlyCoolingTou) -> None:
    impl.trigger_top_event(LocalControlTopEvent.MonitorOnly)
    assert impl.top_state == LocalControlTopState.Monitor
    impl.trigger_top_event(LocalControlTopEvent.MonitorAndControl)
    assert impl.top_state == LocalControlTopState.Normal
    impl.trigger_top_event(LocalControlTopEvent.TopGoDormant)
    assert impl.top_state == LocalControlTopState.Dormant
    impl.trigger_top_event(LocalControlTopEvent.TopWakeUp)
    assert impl.top_state == LocalControlTopState.Normal  # HACK: wake resumes control

    states = [p for _, p in impl.sent if isinstance(p, SingleMachineState)]
    assert [s.State for s in states] == [
        LocalControlTopState.Monitor,
        LocalControlTopState.Normal,
        LocalControlTopState.Dormant,
        LocalControlTopState.Normal,
    ]
    assert all(s.StateEnum == LocalControlTopState.enum_name() for s in states)


# ---- the schedule at its boundaries ----


def dt(day: int, hour: int, minute: int) -> datetime:
    # 2026-08-10 is a Monday; day is the calendar day in that week
    return ET.localize(datetime(2026, 8, day, hour, minute))


def test_hp_should_be_on_boundaries(impl: NolanBufferOnlyCoolingTou) -> None:
    on = impl.hp_should_be_on
    assert on(dt(15, 12, 0))  # Saturday, mid-on-peak hours: weekend ON
    assert on(dt(10, 6, 59))  # weekday pre-peak
    assert not on(dt(10, 7, 0))  # on-peak opens
    assert not on(dt(10, 11, 59))
    assert on(dt(10, 12, 0))  # midday shoulder
    assert not on(dt(10, 16, 0))  # evening peak
    assert not on(dt(10, 19, 59))
    assert on(dt(10, 20, 0))  # evening peak closes


# ---- the TOU loop against the spruce plant records ----


def fsm_events(impl: NolanBufferOnlyCoolingTou) -> list[tuple[str, str]]:
    return [(dst, p.EventName) for dst, p in impl.sent if isinstance(p, FsmEvent)]


def test_resolves_spruce_plant_targets(spruce_impl: NolanBufferOnlyCoolingTou) -> None:
    assert spruce_impl.layout.iso_valve.name == NolanNodeNames.iso_valve_relay
    assert spruce_impl.layout.secondary_pump_relay.name == NolanNodeNames.secondary_pump_relay
    assert spruce_impl.layout.hp_scada_ops_relay.name == HSNN.hp_scada_ops_relay
    assert sorted(
        c.CircuitPosition for c, _, _ in spruce_impl._held_circuit_relays
    ) == [
        1,
        2,
        4,
    ]


def test_on_and_off_sequencing(
    spruce_impl: NolanBufferOnlyCoolingTou, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(NolanBufferOnlyCoolingTou, "SEQUENCE_STEP_S", 0.01)
    asyncio.run(spruce_impl.sequence_hp_on())
    on_targets = [dst for dst, _ in fsm_events(spruce_impl)]
    assert on_targets == [
        NolanNodeNames.iso_valve_relay,
        NolanNodeNames.secondary_pump_relay,
        HSNN.hp_boss,
    ]
    spruce_impl.sent.clear()
    asyncio.run(spruce_impl.sequence_hp_off())
    off_targets = [dst for dst, _ in fsm_events(spruce_impl)]
    assert off_targets == [
        HSNN.hp_boss,
        NolanNodeNames.secondary_pump_relay,
    ]


def test_zone_holds_command_failsafe_and_release_ops(
    spruce_impl: NolanBufferOnlyCoolingTou,
) -> None:
    spruce_impl.command_zone_holds()
    targets = [dst for dst, _ in fsm_events(spruce_impl)]
    assert targets == [
        "zone1-bedrooms-failsafe-relay",
        "zone1-bedrooms-ops-relay",
        "zone2-living-rm-failsafe-relay",
        "zone2-living-rm-ops-relay",
        "zone4-garage-failsafe-relay",
        "zone4-garage-ops-relay",
    ]


def test_missing_plant_node_is_a_crash_not_a_degrade(
    app: ScadaApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gw.nolan.layout axiom 3 forces the plant nodes to exist at decode;
    if construction ever sees one missing anyway (contract bypassed), the
    actor must crash — never run partially blind."""
    monkeypatch.setattr(NolanBufferOnlyCoolingTou, "REQUIRED_NODES", ("no-such-node",))
    with pytest.raises(ValueError, match="required node no-such-node"):
        LocalControl(LC_NAME, app)


def test_layout_without_plant_nodes_fails_decode() -> None:
    """The prevention itself: a Nolan layout missing a plant relay node is
    INVALID — axiom 5 (RequiredActuators) rejects it at decode, on the
    same static+ops assembly path the boot uses. The counterexample is
    built by typed mutation of a valid decode, re-validated at the
    boundary."""
    config = Path(__file__).parent.parent / "config"
    ops = OperationalParams.model_validate_json(
        (config / "gw.nolan.operational.params.json").read_text()
    )
    layout = NolanLayout.model_validate(
        assemble_runtime_layout(
            json.loads((config / "gw.nolan.layout.json").read_text()),
            ops.model_dump(by_alias=True, exclude_none=True),
        )
    )
    layout.ShNodes = [
        n for n in layout.ShNodes if n.Name != NolanNodeNames.iso_valve_relay
    ]
    with pytest.raises(ValueError, match="Axiom 5 \\(RequiredActuators\\)"):
        NolanLayout.model_validate(layout.model_dump(by_alias=True, exclude_none=True))


# ---- NolanBufferOnlyTou: the heating machine, on the Nolan sim pair ----


def heating_ops(tmp_path: Path) -> Path:
    """The spruce ops word authored for the heating machine: Heating,
    BufferOnly, the band at 130/90 as the fixture carries it."""
    ops = json.loads(SPRUCE_OPS.read_text())
    ops["ServiceMode"] = ServiceMode.Heating.value
    ops["FamilyParams"]["SeasonalStorageMode"] = SeasonalStorageMode.BufferOnly.value
    path = tmp_path / "gw.nolan.operational.params.json"
    path.write_text(json.dumps(ops))
    return path


@pytest.fixture
def heat(tmp_path: Path) -> NolanBufferOnlyTou:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    settings.paths.operational_params = heating_ops(tmp_path)
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    lc = LocalControl(LC_NAME, scada_app)
    assert isinstance(lc._impl, NolanBufferOnlyTou)
    inner = lc._impl
    inner.sent = []
    inner._send_to = lambda dst, payload, src=None: inner.sent.append(
        (dst.name, payload)
    )
    return inner


def commands(actor: NolanBufferOnlyTou) -> list[tuple[str, str]]:
    return [(dst, p.EventName) for dst, p in actor.sent if isinstance(p, FsmEvent)]


def hp_boss_events(actor: NolanBufferOnlyTou) -> list[FsmEvent]:
    return [
        p for dst, p in actor.sent
        if isinstance(p, FsmEvent) and dst == HSNN.hp_boss
    ]


def call_states(actor: NolanBufferOnlyTou) -> list[str]:
    return [
        p.State
        for _, p in actor.sent
        if isinstance(p, SingleMachineState)
        and p.StateEnum == NolanLcBufferOnlyState.enum_name()
    ]


def read_at(
    actor: NolanBufferOnlyTou, channel_name: str, value: int | None, age_s: float = 0
) -> None:
    """A reading of the channel taken age_s ago; None is no reading."""
    actor.data.latest_channel_values[channel_name] = value
    actor.data.latest_channel_unix_ms[channel_name] = (
        None if value is None else int((time.time() - age_s) * 1000)
    )


def buffer_at(
    actor: NolanBufferOnlyTou, depth1_f: float, depth3_f: float, age_s: float = 0
) -> None:
    for name, f in ((HCN.buffer.depth1, depth1_f), (HCN.buffer.depth3, depth3_f)):
        raw = actor.layout.channel_registry.temperature_from_f(name, f).raw
        read_at(actor, name, raw, age_s)


OFFPEAK = dt(10, 13, 0)  # Monday 13:00, the midday shoulder
ONPEAK = dt(10, 17, 0)  # Monday 17:00, the evening peak

ZONE_RELEASE = [
    (f"zone{z}-{name}-failsafe-relay", ChangeZoneCallSource.SwitchToWallThermostat.value)
    if kind == "failsafe"
    else (f"zone{z}-{name}-ops-relay", ChangeRelayState.OpenRelay.value)
    for z, name in (
        (1, "bedrooms"),
        (2, "living-rm"),
        (3, "upstairs"),
        (4, "garage"),
        (5, "living-rm-fancoil"),
    )
    for kind in ("failsafe", "ops")
]
STORE_CLOSED = [
    (NolanNodeNames.charge_valve_relay, ChangeValveState.CloseValve.value),
    (HSNN.store_pump_relay, ChangeRelayState.OpenRelay.value),
]
PUMP_ON = [
    (NolanNodeNames.secondary_pump_relay, ChangeRelayState.CloseRelay.value),
    (NolanNodeNames.iso_valve_relay, ChangeValveState.OpenValve.value),
]
PUMP_OFF = [
    (NolanNodeNames.secondary_pump_relay, ChangeRelayState.OpenRelay.value),
    (NolanNodeNames.iso_valve_relay, ChangeValveState.CloseValve.value),
]
CALL_ON = [(HSNN.hp_boss, TurnHpOnOff.TurnOn.value)]
CALL_OFF = [(HSNN.hp_boss, TurnHpOnOff.TurnOff.value)]


def test_heating_layout_selects_buffer_only_tou(heat: NolanBufferOnlyTou) -> None:
    assert heat.top_state == LocalControlTopState.Normal
    assert heat.call_state == NolanLcBufferOnlyState.Initializing


def test_heating_unknown_heat_pump_fails_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Nolan layout whose hp-odu device type has no traits row
    stops the scada at construction, naming the device type."""
    monkeypatch.delitem(HP_TRAITS, "SimHpOdu")
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    settings.paths.operational_params = heating_ops(tmp_path)
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    with pytest.raises(ValueError, match="SimHpOdu"):
        scada_app.instantiate()


def test_heating_boot_posture(heat: NolanBufferOnlyTou) -> None:
    """After ActuatorsReady: every zone on its thermostat with the scada
    relay open, the store circuit closed, the call open, and the secondary
    pump on with the iso valve open because the heat-pump power is not
    known yet. The machine reports HpCallOff and nothing more."""
    heat.on_actuators_ready()
    assert commands(heat) == ZONE_RELEASE + STORE_CLOSED + CALL_OFF + PUMP_ON
    assert call_states(heat) == [NolanLcBufferOnlyState.HpCallOff]
    assert all(e.FromHandle == heat.normal_node.handle for e in hp_boss_events(heat))


def test_heating_band_latch(heat: NolanBufferOnlyTou) -> None:
    """depth3 at the full threshold sets full; depth1 below the charge
    threshold clears it; between the two the latch holds."""
    heat.on_actuators_ready()
    buffer_at(heat, 100, 100)
    heat.update_band()
    assert not heat.buffer_full
    buffer_at(heat, 120, 130)
    heat.update_band()
    assert heat.buffer_full
    buffer_at(heat, 95, 110)
    heat.update_band()
    assert heat.buffer_full
    buffer_at(heat, 89, 110)
    heat.update_band()
    assert not heat.buffer_full
    buffer_at(heat, 100, 129)
    heat.update_band()
    assert not heat.buffer_full


def test_heating_call_follows_tariff_and_band(heat: NolanBufferOnlyTou) -> None:
    heat.on_actuators_ready()
    buffer_at(heat, 80, 80)
    heat.sent.clear()
    heat.check(OFFPEAK)
    assert commands(heat) == CALL_ON
    assert call_states(heat) == [NolanLcBufferOnlyState.HpCallOn]
    heat.sent.clear()
    heat.check(OFFPEAK)
    assert commands(heat) == []
    heat.check(ONPEAK)
    assert commands(heat) == CALL_OFF
    assert call_states(heat) == [NolanLcBufferOnlyState.HpCallOff]
    heat.sent.clear()
    buffer_at(heat, 120, 130)  # full
    heat.check(OFFPEAK)
    assert commands(heat) == []
    buffer_at(heat, 85, 110)  # wants charge again
    heat.check(OFFPEAK)
    assert commands(heat) == CALL_ON
    heat.sent.clear()
    buffer_at(heat, 120, 130)  # full while the call is on
    heat.check(OFFPEAK)
    assert commands(heat) == CALL_OFF


def test_heating_call_opens_before_onpeak(heat: NolanBufferOnlyTou) -> None:
    """The call opens the heat pump's call-open lead before an on-peak
    window (two minutes for the sim row), and closes again at the window's
    own end."""
    assert heat.traits.call_open_lead_s == 120
    heat.on_actuators_ready()
    buffer_at(heat, 80, 80)
    heat.sent.clear()
    heat.check(dt(10, 15, 57))  # three minutes before the evening peak
    assert commands(heat) == CALL_ON
    heat.sent.clear()
    heat.check(dt(10, 15, 58))  # the lead: on-peak starts in two minutes
    assert commands(heat) == CALL_OFF
    heat.sent.clear()
    heat.check(dt(10, 16, 0))
    assert commands(heat) == []
    heat.check(dt(10, 19, 59))
    assert commands(heat) == []
    heat.check(dt(10, 20, 0))  # the end is not padded
    assert commands(heat) == CALL_ON


def test_heating_pump_follows_power(heat: NolanBufferOnlyTou) -> None:
    """Secondary pump and iso valve: on above the on-threshold, off on the
    first read below the off-threshold, held between, on when the power is
    unknown. Not a function of the call."""
    heat.on_actuators_ready()
    buffer_at(heat, 120, 130)  # full, so the call stays off throughout
    heat.sent.clear()
    read_at(heat, HCN.hp_odu_pwr, 50)
    heat.check(ONPEAK)
    assert commands(heat) == PUMP_OFF
    heat.sent.clear()
    read_at(heat, HCN.hp_odu_pwr, 300)
    heat.check(ONPEAK)
    assert commands(heat) == []
    read_at(heat, HCN.hp_odu_pwr, 600)
    heat.check(ONPEAK)
    assert commands(heat) == PUMP_ON
    heat.sent.clear()
    read_at(heat, HCN.hp_odu_pwr, 300)
    heat.check(ONPEAK)
    assert commands(heat) == []
    read_at(heat, HCN.hp_odu_pwr, 50)
    heat.check(ONPEAK)
    assert commands(heat) == PUMP_OFF
    heat.sent.clear()
    read_at(heat, HCN.hp_odu_pwr, None)
    heat.check(ONPEAK)
    assert commands(heat) == PUMP_ON


def test_heating_scada_blind(heat: NolanBufferOnlyTou) -> None:
    """Either buffer channel stale beyond five minutes blinds the band: the
    scada-blind node drives the call on the schedule alone; both fresh
    again re-boots Normal."""
    heat.on_actuators_ready()
    buffer_at(heat, 80, 80)
    heat.check(OFFPEAK)
    assert heat.call_state == NolanLcBufferOnlyState.HpCallOn
    heat.sent.clear()
    buffer_at(heat, 80, 80, age_s=301)
    heat.check(OFFPEAK)
    assert heat.top_state == LocalControlTopState.ScadaBlind
    assert call_states(heat) == [NolanLcBufferOnlyState.Dormant]
    assert commands(heat) == []  # off-peak: the call stays closed
    heat.check(ONPEAK)
    assert commands(heat) == CALL_OFF
    assert hp_boss_events(heat)[-1].FromHandle == heat.layout.local_control_scada_blind_node.handle
    heat.sent.clear()
    heat.check(OFFPEAK)
    assert commands(heat) == CALL_ON  # the schedule alone, blind to the band
    heat.sent.clear()
    buffer_at(heat, 120, 130)  # fresh again, and full
    heat.check(OFFPEAK)
    assert heat.top_state == LocalControlTopState.Normal
    assert call_states(heat) == [
        NolanLcBufferOnlyState.Initializing,
        NolanLcBufferOnlyState.HpCallOff,
    ]
    assert commands(heat) == ZONE_RELEASE + STORE_CLOSED + CALL_OFF + PUMP_ON
    assert all(e.FromHandle == heat.normal_node.handle for e in hp_boss_events(heat))


def test_heating_dormant_and_wake(heat: NolanBufferOnlyTou) -> None:
    """Admin takes the tree: Dormant, nothing commanded. Release re-boots:
    Initializing and the boot posture, never a resumed call."""
    heat.on_actuators_ready()
    buffer_at(heat, 80, 80)
    heat.check(OFFPEAK)
    assert heat.call_state == NolanLcBufferOnlyState.HpCallOn
    heat.sent.clear()
    for node in heat.my_actuators():  # admin has taken the tree
        node.Handle = f"admin.{node.Name}"
    heat.go_dormant()
    assert heat.top_state == LocalControlTopState.Dormant
    assert heat.call_state == NolanLcBufferOnlyState.Dormant
    assert commands(heat) == []
    heat.check(OFFPEAK)
    assert commands(heat) == []
    heat.sent.clear()
    for node in heat.layout.actuators:  # the scada hands the tree back first
        node.Handle = f"{heat.node.handle}.{node.Name}"
    heat.wake_up()
    assert heat.top_state == LocalControlTopState.Normal
    assert call_states(heat) == [
        NolanLcBufferOnlyState.Initializing,
        NolanLcBufferOnlyState.HpCallOff,
    ]
    assert commands(heat) == ZONE_RELEASE + STORE_CLOSED + CALL_OFF + PUMP_ON
