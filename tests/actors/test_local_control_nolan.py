"""Nolan local control: which machine the loader selects for a Nolan
layout, the layout axiom that rejects a plant-incomplete layout at decode,
and NolanBufferOnlyTou, the heating machine."""

import json
import time
from datetime import datetime
from pathlib import Path

import pytest
import pytz
from gwproto.message import Header, Message
from pydantic import ValidationError

from actors.hp_boss.sensing import HP_TRAITS, HpTraits, validated_hp_traits
from actors.in_process_messages import MachineStateSubscribe
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control_loader import LocalControl
from gwsproto.enums import (
    ChangeRelayState,
    ChangeValveState,
    ChangeZoneCallSource,
    DeviceType,
    DispatchRefusalReason,
    LocalControlTopState,
    NolanLcBufferOnlyState,
    SeasonalStorageMode,
    ServiceMode,
    SimDeviceType,
    SpruceHackHpState,
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


def app_with(tmp_path: Path, service: ServiceMode, storage: SeasonalStorageMode) -> ScadaApp:
    ops = json.loads(SPRUCE_OPS.read_text())
    ops["ServiceMode"] = service.value
    ops["FamilyParams"]["SeasonalStorageMode"] = storage.value
    path = tmp_path / "gw.nolan.operational.params.json"
    path.write_text(json.dumps(ops))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    settings.paths.operational_params = path
    settings.paths.mkdirs()
    return ScadaApp(app_settings=settings)


def test_nolan_all_tanks_selects_no_machine(tmp_path: Path) -> None:
    """A Nolan layout has a heating machine only for BufferOnly; AllTanks
    raises at selection."""
    scada_app = app_with(tmp_path, ServiceMode.Heating, SeasonalStorageMode.AllTanks)
    with pytest.raises(Exception, match="No local control machine"):
        scada_app.instantiate()


@pytest.mark.parametrize("storage", list(SeasonalStorageMode))
def test_nolan_cooling_is_not_implemented(tmp_path: Path, storage: SeasonalStorageMode) -> None:
    """A Nolan layout out of standby that authors Cooling stops at selection."""
    scada_app = app_with(tmp_path, ServiceMode.Cooling, storage)
    with pytest.raises(NotImplementedError, match="no cooling machine"):
        scada_app.instantiate()


def test_missing_plant_node_is_a_crash_not_a_degrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gw.nolan.layout axiom 5 forces the plant nodes to exist at decode;
    if construction ever sees one missing anyway, the actor crashes rather
    than run partially blind."""
    monkeypatch.setattr(NolanBufferOnlyTou, "REQUIRED_NODES", ("no-such-node",))
    scada_app = app_with(tmp_path, ServiceMode.Heating, SeasonalStorageMode.BufferOnly)
    with pytest.raises(ValueError, match="required node no-such-node"):
        scada_app.instantiate()


def dt(day: int, hour: int, minute: int) -> datetime:
    # 2026-08-10 is a Monday; day is the calendar day in that week
    return ET.localize(datetime(2026, 8, day, hour, minute))


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


@pytest.mark.parametrize(
    "service, standby",
    [(ServiceMode.Heating, False), (ServiceMode.Cooling, False), (ServiceMode.Heating, True)],
)
def test_unknown_heat_pump_stops_the_scada_at_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, service: ServiceMode, standby: bool
) -> None:
    """A Nolan layout whose hp-odu device type has no traits row stops the
    scada at load in every local-control selection, naming the device type,
    the supported heat pumps and where the row goes."""
    monkeypatch.delitem(HP_TRAITS, SimDeviceType.SimHpOdu)
    ops = json.loads(SPRUCE_OPS.read_text())
    ops["ServiceMode"] = service.value
    ops["Standby"] = standby
    if standby:
        ops["AcceptsDispatch"] = False
        ops["DispatchRefusalReason"] = DispatchRefusalReason.Standby.value
    ops["FamilyParams"]["SeasonalStorageMode"] = SeasonalStorageMode.BufferOnly.value
    ops_path = tmp_path / "gw.nolan.operational.params.json"
    ops_path.write_text(json.dumps(ops))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    settings.paths.operational_params = ops_path
    settings.paths.mkdirs()
    with pytest.raises(
        ValueError, match=r"SimHpOdu.*SamsungAE055FCYDCG.*actors/hp_boss/sensing\.py"
    ):
        ScadaApp(app_settings=settings).instantiate()


def test_hp_traits_keyed_by_device_type_members() -> None:
    assert all(isinstance(k, (DeviceType, SimDeviceType)) for k in HP_TRAITS)


def test_hp_traits_rows_go_through_their_formats() -> None:
    with pytest.raises(ValidationError):
        validated_hp_traits({DeviceType.SamsungAE055FCYDCG: HpTraits(500, -1, 120)})


def test_hp_traits_off_line_below_on_line() -> None:
    with pytest.raises(ValueError, match="off line 500 W is not below on line 80 W"):
        validated_hp_traits({DeviceType.SamsungAE055FCYDCG: HpTraits(80, 500, 120)})


def test_heating_boot_posture(heat: NolanBufferOnlyTou) -> None:
    """After ActuatorsReady: every zone on its thermostat with the scada
    relay open, the store circuit closed, the call open, and the secondary
    pump on with the iso valve open because no hp-sensor state has
    arrived yet. The machine reports HpCallOff and nothing more."""
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


def hp_sensor_says(actor: NolanBufferOnlyTou, state: SpruceHackHpState) -> None:
    """The hp-sensor state as the scada forwards it to a subscriber."""
    payload = SingleMachineState(
        MachineHandle=HSNN.hp_sensor,
        StateEnum=SpruceHackHpState.enum_name(),
        State=state,
        UnixMs=int(time.time() * 1000),
    )
    actor.process_message(
        Message(
            header=Header(Src=HSNN.hp_sensor, Dst=actor.name, MessageType=payload.TypeName),
            Payload=payload,
        )
    )


@pytest.mark.asyncio
async def test_heating_subscribes_to_hp_sensor_at_start(heat: NolanBufferOnlyTou) -> None:
    heat._stop_requested = True  # the two loops end at once
    heat._send = lambda message: None  # the watchdog pat
    heat.start()
    assert [
        (dst, p.NodeName) for dst, p in heat.sent if isinstance(p, MachineStateSubscribe)
    ] == [(CoreNodeNames.primary_scada, HSNN.hp_sensor)]


def test_heating_pump_follows_hp_sensor(heat: NolanBufferOnlyTou) -> None:
    """Secondary pump and iso valve follow the hp-sensor state the moment
    it arrives, with no check in between: off in HpDetectedOff, on in
    HpDetectedOn and in Unknown, and on before any state has arrived. Not
    a function of the call, and the watts are not read."""
    heat.on_actuators_ready()
    assert commands(heat)[-2:] == PUMP_ON
    buffer_at(heat, 120, 130)  # full, so the call stays off throughout
    heat.sent.clear()
    hp_sensor_says(heat, SpruceHackHpState.HpDetectedOff)
    assert commands(heat) == PUMP_OFF
    heat.sent.clear()
    read_at(heat, HCN.hp_odu_pwr, 600)
    heat.check(ONPEAK)
    hp_sensor_says(heat, SpruceHackHpState.HpDetectedOff)
    assert commands(heat) == []
    hp_sensor_says(heat, SpruceHackHpState.HpDetectedOn)
    assert commands(heat) == PUMP_ON
    heat.sent.clear()
    hp_sensor_says(heat, SpruceHackHpState.Unknown)
    read_at(heat, HCN.hp_odu_pwr, 50)
    heat.check(ONPEAK)
    assert commands(heat) == []
    hp_sensor_says(heat, SpruceHackHpState.HpDetectedOff)
    assert commands(heat) == PUMP_OFF
    heat.sent.clear()
    hp_sensor_says(heat, SpruceHackHpState.Unknown)
    assert commands(heat) == PUMP_ON


def test_heating_hp_sensor_state_while_dormant_waits_for_the_wake(
    heat: NolanBufferOnlyTou,
) -> None:
    """While admin holds the tree a state is kept and nothing is
    commanded; the boot on release commands the pump by it."""
    heat.on_actuators_ready()
    for node in heat.my_actuators():  # admin has taken the tree
        node.Handle = f"admin.{node.Name}"
    heat.go_dormant()
    heat.sent.clear()
    hp_sensor_says(heat, SpruceHackHpState.HpDetectedOff)
    assert commands(heat) == []
    for node in heat.layout.actuators:  # the scada hands the tree back first
        node.Handle = f"{heat.node.handle}.{node.Name}"
    heat.wake_up()
    assert commands(heat) == ZONE_RELEASE + STORE_CLOSED + CALL_OFF + PUMP_OFF


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
