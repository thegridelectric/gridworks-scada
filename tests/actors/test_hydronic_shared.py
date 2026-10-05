"""The family-neutral hydronic surface (`actors/hydronic/shared.py`) on the
sim House0 and Nolan pairs: a zone-call circuit's relays are the ones it
names, the commands emitted for a circuit target the right relay from the
right boss, a caller who is not the boss sends nothing, and the TOU judgment
reads the tariff's windows."""

import datetime as real_datetime
import uuid
from pathlib import Path

import pytest

import actors.hydronic.shared as shared
from actors.pico_cycler import PicoCycler
from gwsproto.conversions.temperature import Temperature
from gwsproto.enums import ChangeZoneCallSource, ChangeRelayState, DayOfWeek, TelemetryName, Unit
from gwsproto.named_types import FsmEvent, TouWindow
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
}


def make_app(pair: str) -> ScadaApp:
    layout, ops = PAIRS[pair]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.fixture(params=sorted(PAIRS))
def actor(request: pytest.FixtureRequest) -> PicoCycler:
    """Any HydronicNode subclass will do; PicoCycler is the smallest and is
    the boss of the vdc relay. Sends are captured, not delivered."""
    app = make_app(request.param)
    pico_cycler = app.get_communicator_as_type(HSNN.pico_cycler, PicoCycler)
    assert pico_cycler is not None
    pico_cycler.sent = []
    pico_cycler._send_to = lambda dst, payload, src=None: pico_cycler.sent.append((dst.name, payload))
    return pico_cycler


def only_event(actor: PicoCycler) -> tuple[str, FsmEvent]:
    assert len(actor.sent) == 1, actor.sent
    dst, payload = actor.sent[0]
    assert isinstance(payload, FsmEvent)
    return dst, payload


# --- zone-call circuit relays ----------------------------------------------


def test_circuit_relays_are_the_ones_it_names(actor: PicoCycler) -> None:
    for circuit in actor.layout.hydronic.ZoneCallCircuits:
        assert actor.stat_failsafe_relay(circuit) is actor.layout.node(circuit.FailsafeRelayNode)
        assert actor.stat_ops_relay(circuit) is actor.layout.node(circuit.OpsRelayNode)


# --- zone relay commands ----------------------------------------------------


@pytest.mark.parametrize(
    ("method", "relay_field", "event_type", "event_name"),
    [
        ("heatcall_ctrl_to_scada", "FailsafeRelayNode", ChangeZoneCallSource, ChangeZoneCallSource.SwitchToScada),
        ("heatcall_ctrl_to_stat", "FailsafeRelayNode", ChangeZoneCallSource, ChangeZoneCallSource.SwitchToWallThermostat),
        ("stat_ops_close_relay", "OpsRelayNode", ChangeRelayState, ChangeRelayState.CloseRelay),
        ("stat_ops_open_relay", "OpsRelayNode", ChangeRelayState, ChangeRelayState.OpenRelay),
    ],
)
def test_circuit_relay_command_from_the_boss(
    actor: PicoCycler, method: str, relay_field: str, event_type, event_name
) -> None:
    """Every circuit, including the Nolan living room's second circuit
    (place 5, serving zone 2), is commanded through the relay it names."""
    boss = actor.layout.node(CoreNodeNames.local_control_normal)  # `n` is the boss of the zone relays at boot
    for circuit in actor.layout.hydronic.ZoneCallCircuits:
        actor.sent = []
        getattr(actor, method)(circuit, command_node=boss)
        dst, event = only_event(actor)
        assert dst == getattr(circuit, relay_field)
        assert event.ToHandle == actor.layout.node(dst).handle
        assert event.FromHandle == boss.handle
        assert event.EventType == event_type.enum_name()
        assert event.EventName == event_name


@pytest.mark.parametrize(
    "method", ["heatcall_ctrl_to_scada", "heatcall_ctrl_to_stat", "stat_ops_close_relay", "stat_ops_open_relay"]
)
def test_circuit_relay_command_sends_nothing_when_not_the_boss(actor: PicoCycler, method: str) -> None:
    # pico-cycler is not the boss of the zone relays: the FsmEvent fails its
    # boss axiom and the helper logs instead of sending.
    for circuit in actor.layout.hydronic.ZoneCallCircuits:
        getattr(actor, method)(circuit)
    assert actor.sent == []


# --- the vdc pair -----------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "event_name"),
    [("close_vdc_relay", ChangeRelayState.CloseRelay), ("open_vdc_relay", ChangeRelayState.OpenRelay)],
)
def test_vdc_relay_command_from_pico_cycler(actor: PicoCycler, method: str, event_name) -> None:
    trigger_id = str(uuid.uuid4())
    getattr(actor, method)(trigger_id=trigger_id)
    dst, event = only_event(actor)
    assert dst == HSNN.vdc_relay
    assert event.ToHandle == actor.layout.vdc_relay.handle
    assert event.FromHandle == actor.node.handle
    assert event.EventName == event_name
    assert event.TriggerId == trigger_id


# --- temperature access ---------------------------------------------------


def test_nolan_zone_temperature_reads_through_its_encoding() -> None:
    """The Nolan sim pair reads zone temperature as `-gw-temp` in
    CelsiusTimes100 and derives the zone `-set` in FahrenheitX100."""
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    pico_cycler = app.get_communicator_as_type(HSNN.pico_cycler, PicoCycler)
    assert pico_cycler is not None
    channel = "zone1-bedrooms-gw-temp"
    assert pico_cycler.layout.channel_registry.unit(channel) == TelemetryName.CelsiusTimes100
    pico_cycler.data.latest_channel_values[channel] = 2000
    temperature = pico_cycler.channel_temperature(channel)
    assert temperature == Temperature(2000, TelemetryName.CelsiusTimes100)
    assert temperature.f == pytest.approx(68.0)
    assert pico_cycler.layout.channel_registry.unit("zone1-bedrooms-set") == Unit.FahrenheitX100


# --- TOU clock --------------------------------------------------------------


def at(monkeypatch: pytest.MonkeyPatch, actor: PicoCycler, weekday: int, hour: int, minute: int) -> None:
    """Pin the module clock: `weekday` 0=Mon..6=Sun, wall time in the actor's zone."""
    base = real_datetime.datetime(2026, 1, 5)  # a Monday
    naive = base + real_datetime.timedelta(days=weekday, hours=hour, minutes=minute)
    fixed = actor.timezone.localize(naive)

    class FixedDatetime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(shared, "datetime", FixedDatetime)


@pytest.mark.parametrize(
    ("weekday", "hour", "minute", "onpeak", "just_before"),
    [
        (0, 8, 0, True, False),     # Monday mid-morning peak
        (0, 6, 57, False, False),   # 3 min out: not yet on-peak, not yet "just before"
        (0, 6, 58, True, True),     # 2 min out: on-peak by the look-ahead, and just before
        (0, 12, 0, False, False),   # mid-day
        (0, 15, 59, True, True),    # look-ahead into the evening peak, and just before it
        (0, 16, 58, True, False),   # inside the evening peak: not "just before" anything
        (0, 19, 30, True, False),   # evening peak
        (0, 20, 0, False, False),
        (5, 8, 0, False, False),    # Saturday: never on-peak
    ],
)
def test_tou_clock(
    actor: PicoCycler, monkeypatch: pytest.MonkeyPatch,
    weekday: int, hour: int, minute: int, onpeak: bool, just_before: bool,
) -> None:
    at(monkeypatch, actor, weekday, hour, minute)
    assert actor.is_onpeak() is onpeak
    assert actor.just_before_onpeak() is just_before


def test_tou_clock_reads_the_ops_words_windows(actor: PicoCycler, monkeypatch: pytest.MonkeyPatch) -> None:
    """The on-peak windows are the ops word's, not a table in the actor: a
    Saturday-only window makes Saturday morning on-peak and Monday not."""
    tariff = actor.ops.Tariff.model_copy(update={"OnPeakWindows": [
        TouWindow(Start="07:00", End="12:00", Days=[DayOfWeek.Saturday]),
    ]})
    saturday_only = actor.ops.model_copy(update={"Tariff": tariff})
    monkeypatch.setattr(actor.data, "ops", saturday_only)
    at(monkeypatch, actor, 5, 8, 0)
    assert actor.is_onpeak() is True
    at(monkeypatch, actor, 5, 6, 58)
    assert actor.just_before_onpeak() is True
    at(monkeypatch, actor, 0, 8, 0)
    assert actor.is_onpeak() is False


def test_just_before_onpeak_needs_a_window_that_day(actor: PicoCycler, monkeypatch: pytest.MonkeyPatch) -> None:
    at(monkeypatch, actor, 5, 6, 58)  # Saturday: no window opens at 7
    assert actor.just_before_onpeak() is False
