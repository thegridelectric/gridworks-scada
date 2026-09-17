"""The family-neutral hydronic surface (`actors/hydronic/shared.py`) on both
sim House0 pairs: the zone-call circuit relays resolve by zone name, the
commands they emit target the right relay from the right boss, a caller who
is not the boss sends nothing, and the TOU/setpoint judgment reads the zone
setpoint and temperature channels."""

import datetime as real_datetime
import uuid
from pathlib import Path

import pytest

import actors.hydronic.shared as shared
from actors.pico_cycler import PicoCycler
from gwsproto.enums import ChangeZoneCallSource, ChangeRelayState, DayOfWeek
from gwsproto.errors import DcError
from gwsproto.named_types import FsmEvent, TouWindow
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
}
ZONE = "main"  # both sim pairs carry the single critical zone zone1-main


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


# --- zone relay lookup ------------------------------------------------------


def test_zone_relays_resolve_by_zone_name(actor: PicoCycler) -> None:
    zone_node = actor.layout.node(f"zone1-{ZONE}")
    assert actor.stat_failsafe_relay(ZONE) is actor.layout.node(f"{zone_node.name}-failsafe-relay")
    assert actor.stat_ops_relay(ZONE) is actor.layout.node(f"{zone_node.name}-ops-relay")


def test_unknown_zone_raises_dc_error(actor: PicoCycler) -> None:
    with pytest.raises(DcError):
        actor.stat_failsafe_relay("attic")
    with pytest.raises(DcError):
        actor.stat_ops_relay("attic")


# --- zone relay commands ----------------------------------------------------


@pytest.mark.parametrize(
    ("method", "relay_suffix", "event_type", "event_name"),
    [
        ("heatcall_ctrl_to_scada", "failsafe-relay", ChangeZoneCallSource, ChangeZoneCallSource.SwitchToScada),
        ("heatcall_ctrl_to_stat", "failsafe-relay", ChangeZoneCallSource, ChangeZoneCallSource.SwitchToWallThermostat),
        ("stat_ops_close_relay", "ops-relay", ChangeRelayState, ChangeRelayState.CloseRelay),
        ("stat_ops_open_relay", "ops-relay", ChangeRelayState, ChangeRelayState.OpenRelay),
    ],
)
def test_zone_relay_command_from_the_boss(
    actor: PicoCycler, method: str, relay_suffix: str, event_type, event_name
) -> None:
    boss = actor.layout.node(CoreNodeNames.local_control_normal)  # `n` is the boss of the zone relays at boot
    getattr(actor, method)(ZONE, command_node=boss)
    dst, event = only_event(actor)
    assert dst == f"zone1-{ZONE}-{relay_suffix}"
    assert event.ToHandle == actor.layout.node(dst).handle
    assert event.FromHandle == boss.handle
    assert event.EventType == event_type.enum_name()
    assert event.EventName == event_name


@pytest.mark.parametrize(
    "method", ["heatcall_ctrl_to_scada", "heatcall_ctrl_to_stat", "stat_ops_close_relay", "stat_ops_open_relay"]
)
def test_zone_relay_command_sends_nothing_when_not_the_boss(actor: PicoCycler, method: str) -> None:
    # pico-cycler is not the boss of the zone relays: the FsmEvent fails its
    # boss axiom and the helper logs instead of sending.
    getattr(actor, method)(ZONE)
    assert actor.sent == []


@pytest.mark.parametrize(
    "method", ["heatcall_ctrl_to_scada", "heatcall_ctrl_to_stat", "stat_ops_close_relay", "stat_ops_open_relay"]
)
def test_zone_relay_command_sends_nothing_for_unknown_zone(actor: PicoCycler, method: str) -> None:
    getattr(actor, method)("attic", command_node=actor.layout.node(CoreNodeNames.local_control_normal))
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


# --- setpoints + system cold ------------------------------------------------


def test_setpoints_at_onpeak_start_come_from_the_layout_zones_only(actor: PicoCycler) -> None:
    actor.data.latest_channel_values[f"zone1-{ZONE}-set"] = 70_000
    actor.data.latest_channel_values["zone9-attic-set"] = 65_000  # not a layout zone
    actor.refresh_setpoints_at_onpeak_start()
    assert actor.setpoints_at_onpeak_start == {f"zone1-{ZONE}": 70_000}


@pytest.mark.parametrize(
    ("onpeak", "setpoint_at_onpeak", "current_setpoint", "temp", "cold"),
    [
        (False, None, 70_000, 68_900, True),   # more than 1F under: cold
        (False, None, 70_000, 69_100, False),  # within 1F: not cold
        (True, 70_000, 74_000, 69_100, False),  # user raised the stat on-peak: judge against the lower
        (True, 74_000, 70_000, 69_100, False),  # user lowered it: judge against the lower
        (True, 74_000, 70_000, 68_900, True),
    ],
)
def test_is_system_cold_judges_the_critical_zone_against_the_lower_setpoint(
    actor: PicoCycler, monkeypatch: pytest.MonkeyPatch,
    onpeak: bool, setpoint_at_onpeak, current_setpoint, temp, cold: bool,
) -> None:
    zone = f"zone1-{ZONE}"
    monkeypatch.setattr(actor, "is_onpeak", lambda: onpeak)
    actor.setpoints_at_onpeak_start = {} if setpoint_at_onpeak is None else {zone: setpoint_at_onpeak}
    actor.data.latest_channel_values[f"{zone}-set"] = current_setpoint
    actor.data.latest_channel_values[f"{zone}-temp"] = temp
    assert actor.is_system_cold() is cold


def test_is_system_cold_is_false_without_a_temperature(actor: PicoCycler, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actor, "is_onpeak", lambda: False)
    actor.data.latest_channel_values[f"zone1-{ZONE}-set"] = 70_000
    assert actor.is_system_cold() is False


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
    saturday_only = actor.ops.model_copy(update={"OnPeakWindows": [
        TouWindow(Start="07:00", End="12:00", Days=[DayOfWeek.Saturday]),
    ]})
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


def test_latest_temps_f_is_the_data_view(actor: PicoCycler) -> None:
    actor.data.latest_temperatures_f["buffer-depth1"] = 123.0
    assert actor.latest_temps_f is actor.data.latest_temperatures_f
