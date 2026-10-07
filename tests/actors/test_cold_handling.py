"""The shared cold handling (`actors/hydronic/cold.py`), in-process on a
House0 and a Nolan sim pair: the judgment of a cold critical zone through
its primary circuit, against a thermostat's setpoint and against a learned
one, the recorded setpoint across a restart, the cold-watch actor's
five-minute latch with its glitch and, with the stores empty, its request
to the scada, the freeze and still-cold-in-backup glitches, and a scada
holding a contract refusing dispatch in its own operational params file.
The local controls make no watch, and a House0 leaf ally declines an offer
only when the house is cold with the stores empty."""

import json
import time
import uuid
from pathlib import Path

import pytest
from gwproto.message import Header, Message

import actors.hydronic.cold as cold
from actors.hydronic.cold import ColdJudgmentNode, ColdWatch
from actors.in_process_messages import BreakServiceContract, HouseCold, HouseWarm, MachineStateSubscribe
from actors.leaf_ally_loader import LeafAlly
from actors.local_control.house0.tou_base import LocalControlTouBase
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control_loader import LocalControl
from actors.scada_data import RECORDED_SETPOINTS_FILE
from gwsproto.conversions.temperature import Temperature
from gwsproto.enums import (
    DispatchRefusalReason,
    LocalControlTopState,
    LogLevel,
    MainAutoState,
    SeasonalStorageMode,
    ServiceMode,
    Unit,
    ZoneSetpointSource,
)
from gwsproto.named_types import (
    AllyGivesUp,
    Glitch,
    HouseOperatingStatus,
    OperationalParams,
    RecordedSetpoints,
    SingleMachineState,
    SlowDispatchContract,
)
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp

LC_NAME = CoreNodeNames.local_control
WATCH_NAME = CoreNodeNames.cold_watch
CONFIG = Path(__file__).parent.parent / "config"
WILLOW = ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")
NOLAN = ("gw.nolan.layout.json", "gw.nolan.operational.params.json")
T0 = 1_760_000_000.0  # a wall-clock second in 2025; the watch takes its time as an argument


def heating_ops(tmp_path: Path, pair: tuple[str, str], **changes) -> Path:
    """The pair's ops word authored for a heating machine that accepts
    dispatch, in a file the scada may write."""
    ops = json.loads((CONFIG / pair[1]).read_text())
    ops["Standby"] = False
    ops["ServiceMode"] = ServiceMode.Heating.value
    ops["FamilyParams"]["SeasonalStorageMode"] = SeasonalStorageMode.BufferOnly.value
    ops["AcceptsDispatch"] = True
    ops.pop("DispatchRefusalReason", None)
    ops.update(changes)
    path = tmp_path / "operational-params.json"
    path.write_text(json.dumps(ops, indent=2))
    return path


def make_app(pair: tuple[str, str], ops_path: Path) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / pair[0]
    settings.paths.operational_params = ops_path
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def cold_watch(app: ScadaApp) -> ColdWatch:
    """The pair's cold watch, its sends captured."""
    watch = app.get_communicator_as_type(WATCH_NAME, ColdWatch)
    assert watch is not None, "cold-watch is constructed in every layout"
    watch.sent = []
    watch._send_to = lambda dst, payload, src=None: watch.sent.append((dst.name, payload))
    return watch


def local_control(watch: ColdWatch) -> ColdJudgmentNode:
    """The heating local control running beside the watch."""
    impl = LocalControl(LC_NAME, watch.services)._impl
    assert isinstance(impl, ColdJudgmentNode)
    return impl


def is_nolan(watch: ColdWatch) -> bool:
    return watch.layout.hydronic.ZoneCallCircuits[0].Name == "bedrooms"


def top_state(watch: ColdWatch, state: LocalControlTopState) -> None:
    """The local control's top state, as the scada forwards it to a
    subscriber."""
    payload = SingleMachineState(
        MachineHandle=watch.layout.node(LC_NAME).handle,
        StateEnum=LocalControlTopState.enum_name(),
        State=state,
        UnixMs=int(T0 * 1000),
    )
    watch.process_message(
        Message(
            header=Header(Src=LC_NAME, Dst=watch.name, MessageType=payload.TypeName),
            Payload=payload,
        )
    )


@pytest.fixture
def willow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ColdWatch:
    """Willow with its one circuit reading its setpoint from the
    thermostat, as a House0 house with a Honeywell does. The fixture
    authors a mechanical dial, whose setpoint is learned."""
    watch = cold_watch(make_app(WILLOW, heating_ops(tmp_path, WILLOW)))
    [circuit] = watch.layout.hydronic.ZoneCallCircuits
    circuit.SetpointSource = ZoneSetpointSource.FromThermostat
    monkeypatch.setattr(watch, "is_onpeak", lambda: False)
    return watch


@pytest.fixture
def nolan(tmp_path: Path) -> ColdWatch:
    return cold_watch(make_app(NOLAN, heating_ops(tmp_path, NOLAN)))


def put_f(actor: ColdWatch, channel: str, f: float | None) -> None:
    """The channel's latest reading, `f` degrees Fahrenheit in the
    channel's own encoding; None is no reading."""
    actor.data.latest_channel_values[channel] = (
        None if f is None else actor.layout.channel_registry.temperature_from_f(channel, f).raw
    )
    actor.data.latest_channel_unix_ms[channel] = None if f is None else int(T0 * 1000)


def calling(actor: ColdWatch, zone: str, is_calling: bool) -> None:
    actor.data.latest_channel_values[f"{zone}-heat-call"] = 1 if is_calling else 0


def glitches(actor: ColdWatch, summary: str) -> list[Glitch]:
    return [p for _, p in actor.sent if isinstance(p, Glitch) and p.Summary == summary]


def breaks(actor: ColdWatch) -> list[BreakServiceContract]:
    return [p for dst, p in actor.sent if isinstance(p, BreakServiceContract)]


def to_local_control(actor: ColdWatch) -> list[HouseCold | HouseWarm]:
    return [
        p for dst, p in actor.sent
        if isinstance(p, (HouseCold, HouseWarm)) and dst == LC_NAME
    ]


# --- the judgment at a thermostat's setpoint (House0) -----------------------

W_ZONE = "zone1-main"


@pytest.mark.parametrize(("temp_f", "is_cold"), [(67.9, True), (68.2, False), (70.0, False)])
def test_a_thermostat_zone_is_cold_two_degrees_under_its_setpoint(
    willow: ColdWatch, temp_f: float, is_cold: bool
) -> None:
    """The willow temperature channel is Celsius x 100, so the readings
    sit a little either side of the 2 F line."""
    put_f(willow, f"{W_ZONE}-set", 70)
    put_f(willow, f"{W_ZONE}-temp", temp_f)
    assert willow.is_system_cold() is is_cold


@pytest.mark.parametrize(
    ("setpoint_at_onpeak_f", "current_setpoint_f", "temp_f", "is_cold"),
    [
        (70, 74, 68.2, False),  # raised on-peak: judged against the lower
        (74, 70, 68.2, False),  # lowered on-peak: judged against the lower
        (74, 70, 67.9, True),
    ],
)
def test_a_thermostat_zone_is_judged_against_the_lower_of_onpeak_start_and_now(
    willow: ColdWatch, monkeypatch: pytest.MonkeyPatch,
    setpoint_at_onpeak_f: float, current_setpoint_f: float, temp_f: float, is_cold: bool,
) -> None:
    monkeypatch.setattr(willow, "is_onpeak", lambda: True)
    registry = willow.layout.channel_registry
    willow.setpoints_at_onpeak_start = {
        f"{W_ZONE}-set": registry.temperature_from_f(f"{W_ZONE}-set", setpoint_at_onpeak_f)
    }
    put_f(willow, f"{W_ZONE}-set", current_setpoint_f)
    put_f(willow, f"{W_ZONE}-temp", temp_f)
    assert willow.is_system_cold() is is_cold


def test_a_zone_with_no_temperature_is_not_judged_cold(willow: ColdWatch) -> None:
    put_f(willow, f"{W_ZONE}-set", 70)
    put_f(willow, f"{W_ZONE}-temp", None)
    assert willow.is_system_cold() is False


def test_a_thermostat_zone_needs_no_heat_call_to_be_cold(willow: ColdWatch) -> None:
    """A thermostat reports its setpoint whether or not it calls, so a
    zone cold with no call (a dead call wire) is still judged."""
    put_f(willow, f"{W_ZONE}-set", 70)
    put_f(willow, f"{W_ZONE}-temp", 60)
    calling(willow, W_ZONE, False)
    assert willow.is_system_cold() is True


def test_setpoints_at_onpeak_start_come_from_the_layout_circuits_only(willow: ColdWatch) -> None:
    put_f(willow, f"{W_ZONE}-set", 70)
    willow.data.latest_channel_values["zone9-attic-set"] = 65_000  # no circuit's setpoint channel
    willow.refresh_setpoints_at_onpeak_start()
    assert willow.setpoints_at_onpeak_start == {
        f"{W_ZONE}-set": willow.layout.channel_registry.temperature_from_f(f"{W_ZONE}-set", 70)
    }


def test_each_channel_is_read_in_its_own_encoding(
    willow: ColdWatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A setpoint held in Fahrenheit x 100 judges a zone temperature read
    in Celsius x 100: 20.5 C is 68.9 F, not 2 F under 70 F; 19.4 C is."""
    monkeypatch.setattr(willow, "is_onpeak", lambda: True)
    willow.setpoints_at_onpeak_start = {f"{W_ZONE}-set": Temperature(7000, Unit.FahrenheitX100)}
    willow.data.latest_channel_values[f"{W_ZONE}-temp"] = 2050
    assert willow.is_system_cold() is False
    willow.data.latest_channel_values[f"{W_ZONE}-temp"] = 1940
    assert willow.is_system_cold() is True


def test_willow_as_authored_is_judged_as_a_learned_zone(tmp_path: Path) -> None:
    """The willow fixture declares a mechanical dial with a learned
    setpoint: cold only while calling, against the recorded setpoint."""
    impl = cold_watch(make_app(WILLOW, heating_ops(tmp_path, WILLOW)))
    put_f(impl, f"{W_ZONE}-set", 70)
    put_f(impl, f"{W_ZONE}-temp", 60)
    impl.cold_watch(T0)
    calling(impl, W_ZONE, False)
    assert impl.is_system_cold() is False
    calling(impl, W_ZONE, True)
    assert impl.is_system_cold() is True


# --- the judgment at a learned setpoint (Nolan) -----------------------------

N_ZONE = "zone1-bedrooms"
N_TEMP = f"{N_ZONE}-gw-temp"
N_SET = f"{N_ZONE}-set"


def test_a_learned_zone_with_no_recorded_setpoint_is_not_judged(nolan: ColdWatch) -> None:
    calling(nolan, N_ZONE, True)
    put_f(nolan, N_TEMP, 50)
    nolan.cold_watch(T0)
    assert nolan.is_system_cold() is False


@pytest.mark.parametrize(
    ("is_calling", "temp_f", "is_cold"),
    [
        (True, 68.0, True),    # calling and 2 F under the record
        (True, 68.1, False),
        (False, 60.0, False),  # no call: a lowered thermostat, not a cold house
        (True, 73.0, False),   # calling above the record: a raised thermostat
    ],
)
def test_a_learned_zone_is_cold_when_calling_two_degrees_under_its_record(
    nolan: ColdWatch, is_calling: bool, temp_f: float, is_cold: bool
) -> None:
    put_f(nolan, N_SET, 70)
    nolan.cold_watch(T0)  # the watch records the setpoint
    calling(nolan, N_ZONE, is_calling)
    put_f(nolan, N_TEMP, temp_f)
    assert nolan.is_system_cold() is is_cold


def test_the_record_outlives_the_generator_withdrawing_its_setpoint(nolan: ColdWatch) -> None:
    """The generator stops emitting and the channel goes quiet; the last
    value it carried is still what a calling zone is judged against."""
    put_f(nolan, N_SET, 70)
    nolan.cold_watch(T0)
    put_f(nolan, N_SET, None)
    calling(nolan, N_ZONE, True)
    put_f(nolan, N_TEMP, 67)
    nolan.cold_watch(T0 + 60)
    assert nolan.is_system_cold() is True


def test_the_record_outlives_a_restart_inside_a_long_heat_call(tmp_path: Path) -> None:
    ops_path = heating_ops(tmp_path, NOLAN)
    first = cold_watch(make_app(NOLAN, ops_path))
    put_f(first, N_SET, 70)
    first.cold_watch(T0)
    record_file = Path(first.settings.paths.data_dir) / RECORDED_SETPOINTS_FILE
    record = RecordedSetpoints.model_validate_json(record_file.read_text())
    assert [(r.ChannelName, r.Value) for r in record.SetpointList] == [(N_SET, 7000)]

    restarted = cold_watch(make_app(NOLAN, ops_path))
    assert restarted.data.latest_channel_values[N_SET] is None
    calling(restarted, N_ZONE, True)
    put_f(restarted, N_TEMP, 67)
    assert restarted.is_system_cold() is True


def test_a_new_setpoint_replaces_the_record(nolan: ColdWatch) -> None:
    put_f(nolan, N_SET, 70)
    nolan.cold_watch(T0)
    put_f(nolan, N_SET, 64)
    nolan.cold_watch(T0 + 60)
    calling(nolan, N_ZONE, True)
    put_f(nolan, N_TEMP, 63)
    assert nolan.is_system_cold() is False
    put_f(nolan, N_TEMP, 61)
    assert nolan.is_system_cold() is True


def test_only_critical_zones_are_judged(nolan: ColdWatch) -> None:
    put_f(nolan, "zone4-garage-set", 70)
    nolan.cold_watch(T0)
    calling(nolan, "zone4-garage", True)
    put_f(nolan, "zone4-garage-gw-temp", 50)
    assert nolan.is_system_cold() is False


# --- a zone is judged through its primary circuit ----------------------------

LIVING = "zone2-living-rm"
FANCOIL = "zone5-living-rm-fancoil"


def test_a_two_circuit_zone_is_judged_on_its_primary_circuit(nolan: ColdWatch) -> None:
    """The living room's floor circuit is its primary and carries the
    thermistor and the setpoint; its fancoil circuit carries neither, and
    a call on it alone does not make the zone cold."""
    put_f(nolan, f"{LIVING}-set", 70)
    nolan.cold_watch(T0)
    put_f(nolan, f"{LIVING}-gw-temp", 66)
    calling(nolan, FANCOIL, True)
    calling(nolan, LIVING, False)
    assert nolan.is_system_cold() is False
    calling(nolan, LIVING, True)
    [zone] = nolan.cold_critical_zones()
    assert zone.zone == "living-rm"


def test_the_judgment_follows_the_circuit_and_not_the_zones_place(nolan: ColdWatch) -> None:
    """With the zones listed in another order, each is still judged on
    its primary circuit's own channels."""
    nolan.layout.hydronic.Zones.reverse()
    put_f(nolan, N_SET, 70)
    nolan.cold_watch(T0)
    calling(nolan, N_ZONE, True)
    put_f(nolan, N_TEMP, 66)
    [zone] = nolan.cold_critical_zones()
    assert zone.zone == "bedrooms"
    assert [r.ChannelName for r in nolan.data.recorded_setpoints.values()] == [N_SET]


def test_the_local_control_judges_against_the_watchs_record(nolan: ColdWatch) -> None:
    lc = local_control(nolan)
    put_f(nolan, N_SET, 70)
    calling(nolan, N_ZONE, True)
    put_f(nolan, N_TEMP, 66)
    assert lc.is_system_cold() is False  # no record yet
    nolan.cold_watch(T0)
    assert lc.is_system_cold() is True


# --- the watch is its own actor ----------------------------------------------


@pytest.mark.asyncio
async def test_the_watch_subscribes_to_the_local_controls_top_state(nolan: ColdWatch) -> None:
    nolan.start()
    nolan.stop()
    assert (nolan.primary_scada.name, MachineStateSubscribe(NodeName=LC_NAME)) in nolan.sent


def test_the_watch_learns_backup_from_the_local_controls_top_state(willow: ColdWatch) -> None:
    assert willow.in_backup is False
    top_state(willow, LocalControlTopState.InBackup)
    assert willow.in_backup is True
    top_state(willow, LocalControlTopState.Normal)
    assert willow.in_backup is False


@pytest.mark.parametrize("lc_class", [LocalControlTouBase, NolanBufferOnlyTou])
def test_a_local_control_makes_no_cold_watch(lc_class: type) -> None:
    assert not hasattr(lc_class, "cold_watch")


# --- the latch ---------------------------------------------------------------


def make_cold(actor: ColdWatch) -> None:
    if is_nolan(actor):
        put_f(actor, N_SET, 70)
        calling(actor, N_ZONE, True)
        put_f(actor, N_TEMP, 66)
    else:
        put_f(actor, f"{W_ZONE}-set", 70)
        put_f(actor, f"{W_ZONE}-temp", 66)


def make_warm(actor: ColdWatch) -> None:
    put_f(actor, N_TEMP if is_nolan(actor) else f"{W_ZONE}-temp", 70)


@pytest.fixture(params=["willow", "nolan"])
def house(request: pytest.FixtureRequest) -> ColdWatch:
    return request.getfixturevalue(request.param)


def test_five_minutes_cold_raises_one_glitch(house: ColdWatch) -> None:
    make_cold(house)
    for elapsed in (0, 60, 120, 180, 240, 299):
        house.cold_watch(T0 + elapsed)
    assert glitches(house, cold.CRITICAL_ZONE_COLD) == []

    house.cold_watch(T0 + cold.COLD_LATCH_S)
    [glitch] = glitches(house, cold.CRITICAL_ZONE_COLD)
    assert glitch.Type == LogLevel.Critical
    assert glitch.Node == WATCH_NAME

    for elapsed in (360, 420, 7200):
        house.cold_watch(T0 + elapsed)
    assert len(glitches(house, cold.CRITICAL_ZONE_COLD)) == 1


def test_five_minutes_cold_with_the_stores_empty_asks_the_scada_once(
    house: ColdWatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(house, "stores_empty", lambda: True)
    make_cold(house)
    for elapsed in (0, 60, 120, 180, 240, 299):
        house.cold_watch(T0 + elapsed)
    assert breaks(house) == []

    house.cold_watch(T0 + cold.COLD_LATCH_S)
    assert [dst for dst, p in house.sent if isinstance(p, BreakServiceContract)] == [
        house.primary_scada.name
    ]
    assert "stores empty" in breaks(house)[0].Cause

    for elapsed in (360, 420, 7200):
        house.cold_watch(T0 + elapsed)
    assert len(breaks(house)) == 1


def test_five_minutes_cold_with_the_stores_empty_tells_the_local_control_on_every_pass(
    house: ColdWatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The watch says what it sees: HouseCold on each pass the latch holds
    with the stores empty, so a machine that could not move when the first
    one came (blind, or dormant under the contract the same look ends)
    moves on the next."""
    monkeypatch.setattr(house, "stores_empty", lambda: True)
    make_cold(house)
    for elapsed in (0, 60, 120, 180, 240, 299):
        house.cold_watch(T0 + elapsed)
    assert to_local_control(house) == []

    house.cold_watch(T0 + cold.COLD_LATCH_S)
    [told] = to_local_control(house)
    assert isinstance(told, HouseCold)
    assert told.Cause == breaks(house)[0].Cause

    for elapsed in (360, 420, 7200):
        house.cold_watch(T0 + elapsed)
    assert [type(p) for p in to_local_control(house)] == [HouseCold] * 4
    assert len(breaks(house)) == 1


def test_a_warm_pass_after_the_cold_message_tells_the_local_control(
    house: ColdWatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(house, "stores_empty", lambda: True)
    make_warm(house)
    house.cold_watch(T0)
    make_cold(house)
    house.cold_watch(T0 + 60)
    make_warm(house)
    house.cold_watch(T0 + 120)
    assert to_local_control(house) == []  # no cold message, so no warm one

    make_cold(house)
    house.cold_watch(T0 + 180)
    house.cold_watch(T0 + 180 + cold.COLD_LATCH_S)
    make_warm(house)
    house.cold_watch(T0 + 240 + cold.COLD_LATCH_S)
    house.cold_watch(T0 + 300 + cold.COLD_LATCH_S)
    assert [type(p) for p in to_local_control(house)] == [HouseCold, HouseWarm]


def test_a_house_cold_with_heat_in_its_stores_breaks_no_contract(
    house: ColdWatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(house, "stores_empty", lambda: False)
    make_cold(house)
    for elapsed in (0, 300, 600, 7200):
        house.cold_watch(T0 + elapsed)
    assert len(glitches(house, cold.CRITICAL_ZONE_COLD)) == 1
    assert breaks(house) == []


def test_stores_emptying_later_in_a_cold_spell_break_the_contract_then(
    house: ColdWatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = [False]
    monkeypatch.setattr(house, "stores_empty", lambda: empty[0])
    make_cold(house)
    for elapsed in (0, 300, 600):
        house.cold_watch(T0 + elapsed)
    assert breaks(house) == []
    empty[0] = True
    house.cold_watch(T0 + 660)
    assert len(breaks(house)) == 1


def test_a_warm_check_lets_the_next_cold_spell_break_again(
    house: ColdWatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(house, "stores_empty", lambda: True)
    make_cold(house)
    house.cold_watch(T0)
    house.cold_watch(T0 + 300)
    make_warm(house)
    house.cold_watch(T0 + 360)
    make_cold(house)
    house.cold_watch(T0 + 420)
    house.cold_watch(T0 + 720)
    assert len(breaks(house)) == 2


@pytest.mark.parametrize(
    ("mode", "buffer_empty", "store_empty", "expected"),
    [
        (SeasonalStorageMode.BufferOnly, True, False, True),
        (SeasonalStorageMode.BufferOnly, False, True, False),
        (SeasonalStorageMode.AllTanks, True, True, True),
        (SeasonalStorageMode.AllTanks, True, False, False),
        (SeasonalStorageMode.AllTanks, False, True, False),
    ],
)
def test_the_stores_are_empty_by_the_seasonal_storage_mode(
    house: ColdWatch, monkeypatch: pytest.MonkeyPatch,
    mode: SeasonalStorageMode, buffer_empty: bool, store_empty: bool, expected: bool,
) -> None:
    ops = house.data.ops
    family = ops.FamilyParams.model_copy(update={"SeasonalStorageMode": mode})
    monkeypatch.setattr(house.data, "ops", ops.model_copy(update={"FamilyParams": family}))
    monkeypatch.setattr(house, "is_buffer_empty", lambda: buffer_empty)
    monkeypatch.setattr(house, "is_storage_empty", lambda: store_empty)
    assert house.stores_empty() is expected


def test_a_warm_check_restarts_the_five_minutes(house: ColdWatch) -> None:
    make_cold(house)
    house.cold_watch(T0)
    house.cold_watch(T0 + 240)
    make_warm(house)
    house.cold_watch(T0 + 270)
    make_cold(house)
    house.cold_watch(T0 + 300)
    house.cold_watch(T0 + 599)
    assert glitches(house, cold.CRITICAL_ZONE_COLD) == []
    house.cold_watch(T0 + 600)
    assert len(glitches(house, cold.CRITICAL_ZONE_COLD)) == 1


def test_a_second_cold_spell_raises_a_second_glitch(house: ColdWatch) -> None:
    make_cold(house)
    house.cold_watch(T0)
    house.cold_watch(T0 + 300)
    make_warm(house)
    house.cold_watch(T0 + 360)
    make_cold(house)
    house.cold_watch(T0 + 420)
    house.cold_watch(T0 + 720)
    assert len(glitches(house, cold.CRITICAL_ZONE_COLD)) == 2


def test_a_nolan_house_stays_in_its_top_state_when_cold(nolan: ColdWatch) -> None:
    lc = local_control(nolan)
    assert isinstance(lc, NolanBufferOnlyTou)
    before = lc.top_state
    make_cold(nolan)
    nolan.cold_watch(T0)
    nolan.cold_watch(T0 + 300)
    assert len(glitches(nolan, cold.CRITICAL_ZONE_COLD)) == 1
    assert lc.top_state == before


# --- still cold in backup, and freezing --------------------------------------


def test_an_hour_cold_in_backup_raises_its_own_glitch_once(willow: ColdWatch) -> None:
    make_cold(willow)
    top_state(willow, LocalControlTopState.InBackup)
    willow.cold_watch(T0)
    willow.cold_watch(T0 + cold.STILL_COLD_IN_BACKUP_S)
    assert glitches(willow, cold.STILL_COLD_IN_BACKUP) == []
    willow.cold_watch(T0 + cold.STILL_COLD_IN_BACKUP_S + 60)
    willow.cold_watch(T0 + cold.STILL_COLD_IN_BACKUP_S + 120)
    [glitch] = glitches(willow, cold.STILL_COLD_IN_BACKUP)
    assert glitch.Type == LogLevel.Critical


def test_a_house_warm_in_backup_raises_no_still_cold_glitch(willow: ColdWatch) -> None:
    make_warm(willow)
    put_f(willow, f"{W_ZONE}-set", 70)
    top_state(willow, LocalControlTopState.InBackup)
    willow.cold_watch(T0)
    willow.cold_watch(T0 + 2 * cold.STILL_COLD_IN_BACKUP_S)
    assert glitches(willow, cold.STILL_COLD_IN_BACKUP) == []


def test_any_circuit_under_the_freeze_line_raises_one_glitch(nolan: ColdWatch) -> None:
    """The garage is not a critical zone and has no recorded setpoint; a
    reading under the freeze line on its circuit is reported all the
    same."""
    put_f(nolan, "zone4-garage-gw-temp", cold.FREEZE_F - 0.5)
    put_f(nolan, N_TEMP, cold.FREEZE_F + 0.5)
    for elapsed in (0, 60, 120):
        nolan.cold_watch(T0 + elapsed)
    [glitch] = glitches(nolan, cold.ZONE_FREEZING)
    assert glitch.Type == LogLevel.Critical
    assert "garage" in glitch.Details


# --- the watch at a house in standby ------------------------------------------


@pytest.fixture
def standby_nolan(tmp_path: Path) -> ColdWatch:
    """The Nolan house in standby, where it may be unheated on purpose."""
    ops_path = heating_ops(
        tmp_path,
        NOLAN,
        Standby=True,
        AcceptsDispatch=False,
        DispatchRefusalReason=DispatchRefusalReason.Standby.value,
    )
    return cold_watch(make_app(NOLAN, ops_path))


def test_a_standby_house_cold_raises_no_critical_zone_cold_glitch(
    standby_nolan: ColdWatch,
) -> None:
    make_cold(standby_nolan)
    for elapsed in (0, cold.COLD_LATCH_S, 7200):
        standby_nolan.cold_watch(T0 + elapsed)
    assert standby_nolan.cold_critical_zones()
    assert glitches(standby_nolan, cold.CRITICAL_ZONE_COLD) == []


def test_a_standby_house_still_reports_a_freezing_circuit(standby_nolan: ColdWatch) -> None:
    put_f(standby_nolan, N_TEMP, cold.FREEZE_F - 0.5)
    standby_nolan.cold_watch(T0)
    [glitch] = glitches(standby_nolan, cold.ZONE_FREEZING)
    assert glitch.Type == LogLevel.Critical


# --- the scada refuses dispatch in its own params file ------------------------


def capture_sends(scada) -> list:
    sent: list = []
    scada._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def under_contract(scada) -> None:
    """The leaf ally holds the command tree under a dispatch contract."""
    scada.auto_state = MainAutoState.LeafTransactiveNode


def test_a_scada_holding_no_contract_breaks_none(tmp_path: Path) -> None:
    ops_path = heating_ops(tmp_path, WILLOW)
    written = ops_path.read_text()
    scada = make_app(WILLOW, ops_path).scada
    sent = capture_sends(scada)
    scada.process_scada_message(scada.layout.node(WATCH_NAME), BreakServiceContract(Cause="cold"))
    assert scada.ops.AcceptsDispatch is True
    assert ops_path.read_text() == written
    assert not [p for _, p in sent if isinstance(p, HouseOperatingStatus)]


@pytest.mark.parametrize("pair", [WILLOW, NOLAN], ids=["willow", "nolan"])
def test_the_scada_writes_the_refusal_and_reports_it(tmp_path: Path, pair: tuple[str, str]) -> None:
    ops_path = heating_ops(tmp_path, pair)
    scada = make_app(pair, ops_path).scada
    sent = capture_sends(scada)
    under_contract(scada)
    watch_node = scada.layout.node(WATCH_NAME)
    scada.report_operating_status()
    assert scada.ops.AcceptsDispatch is True

    scada.process_scada_message(watch_node, BreakServiceContract(Cause="zone1 is cold"))
    assert scada.ops.AcceptsDispatch is False
    assert scada.ops.DispatchRefusalReason == DispatchRefusalReason.ServiceContractBroken
    on_disk = OperationalParams.model_validate_json(ops_path.read_text())
    assert on_disk == scada.ops
    statuses = [p for _, p in sent if isinstance(p, HouseOperatingStatus)]
    assert [(s.AcceptsDispatch, s.DispatchRefusalReason) for s in statuses] == [
        (True, None),
        (False, DispatchRefusalReason.ServiceContractBroken),
    ]

    # A second request changes nothing.
    written = ops_path.read_text()
    scada.process_scada_message(watch_node, BreakServiceContract(Cause="zone1 is cold"))
    assert ops_path.read_text() == written
    assert len([p for _, p in sent if isinstance(p, HouseOperatingStatus)]) == 2


def test_the_refusal_changes_nothing_else_in_the_params_file(tmp_path: Path) -> None:
    ops_path = heating_ops(tmp_path, NOLAN)
    before = json.loads(ops_path.read_text())
    scada = make_app(NOLAN, ops_path).scada
    capture_sends(scada)
    under_contract(scada)
    scada.process_scada_message(scada.layout.node(WATCH_NAME), BreakServiceContract(Cause="cold"))
    after = json.loads(ops_path.read_text())
    assert after.pop("DispatchRefusalReason") == DispatchRefusalReason.ServiceContractBroken.value
    assert after.pop("AcceptsDispatch") is False
    assert before.pop("AcceptsDispatch") is True
    assert after == before


def test_a_house_already_refusing_dispatch_keeps_its_own_reason(tmp_path: Path) -> None:
    ops_path = heating_ops(
        tmp_path, NOLAN, AcceptsDispatch=False,
        DispatchRefusalReason=DispatchRefusalReason.NoAggregator.value,
    )
    written = ops_path.read_text()
    scada = make_app(NOLAN, ops_path).scada
    capture_sends(scada)
    under_contract(scada)
    scada.process_scada_message(scada.layout.node(WATCH_NAME), BreakServiceContract(Cause="cold"))
    assert scada.ops.DispatchRefusalReason == DispatchRefusalReason.NoAggregator
    assert ops_path.read_text() == written


def test_the_refusal_holds_across_a_restart_until_the_file_accepts_dispatch(tmp_path: Path) -> None:
    """Warm again does not clear it: nothing but the params file does."""
    ops_path = heating_ops(tmp_path, NOLAN)
    scada = make_app(NOLAN, ops_path).scada
    capture_sends(scada)
    under_contract(scada)
    scada.process_scada_message(scada.layout.node(WATCH_NAME), BreakServiceContract(Cause="cold"))

    restarted = make_app(NOLAN, ops_path).scada
    assert restarted.ops.AcceptsDispatch is False
    assert restarted.ops.DispatchRefusalReason == DispatchRefusalReason.ServiceContractBroken

    cleared = json.loads(ops_path.read_text())
    cleared["AcceptsDispatch"] = True
    del cleared["DispatchRefusalReason"]
    ops_path.write_text(json.dumps(cleared, indent=2))
    assert make_app(NOLAN, ops_path).scada.ops.AcceptsDispatch is True


# --- the leaf allies decline an offer when cold with the stores empty -------


@pytest.mark.parametrize("mode", [SeasonalStorageMode.BufferOnly, SeasonalStorageMode.AllTanks])
@pytest.mark.parametrize("empty", [True, False])
def test_a_house0_leaf_ally_declines_an_offer_only_when_cold_with_the_stores_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: SeasonalStorageMode, empty: bool
) -> None:
    ops_path = heating_ops(tmp_path, WILLOW)
    ops = json.loads(ops_path.read_text())
    ops["FamilyParams"]["SeasonalStorageMode"] = mode.value
    ops_path.write_text(json.dumps(ops, indent=2))
    ally = LeafAlly(CoreNodeNames.leaf_ally, make_app(WILLOW, ops_path))._impl
    sent: list = []
    monkeypatch.setattr(ally, "_send_to", lambda dst, payload, src=None: sent.append(payload))
    monkeypatch.setattr(ally, "is_system_cold", lambda: True)
    monkeypatch.setattr(ally, "stores_empty", lambda: empty)
    ally.process_slow_dispatch_contract(
        ally.primary_scada,
        SlowDispatchContract(
            ScadaAlias=ally.layout.scada_g_node_alias,
            StartS=(int(time.time()) // 300) * 300 + 300,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4()),
        ),
    )
    declined = [p for p in sent if isinstance(p, AllyGivesUp) and "cold" in p.Reason.lower()]
    assert bool(declined) is empty
