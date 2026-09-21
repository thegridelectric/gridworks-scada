"""The House0 plant surface (`actors/hydronic/house0.py`) on both sim House0
pairs. Choreography: every command lands on the right relay from the boss,
with the right event, and nothing is sent by a caller who is not the boss.
Judgment: the pure readers (energy, power, defrost, store flow) and the
temperature pass (`get_temperatures` with the shared store scrub-and-fill)
pinned on the sim channels."""

import time
from pathlib import Path

import pytest

import actors.hydronic.house0 as house0_module
from actors.hydronic.house0 import House0Hydronic
from gwsproto.enums import (
    ChangeAquastatControl,
    ChangeHeatPumpControl,
    ChangeKeepSend,
    ChangePrimaryPumpControl,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    StoreFlowRelay,
    TurnHpOnOff,
)
from gwsproto.named_types import FsmEvent, Glitch, HeatingForecast, SingleMachineState
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": (
        "gw.house0.willow.layout.json",
        "gw.house0.willow.operational.params.json",
    ),
    "house0-orange": (
        "gw.house0.orange.layout.json",
        "gw.house0.orange.operational.params.json",
    ),
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
def actor(request: pytest.FixtureRequest) -> House0Hydronic:
    """The local-control implementation the facade picked for the sim pair
    is a House0Hydronic; sends are captured, not delivered."""
    app = make_app(request.param)
    impl = app.get_communicator(CoreNodeNames.local_control)._impl
    assert isinstance(impl, House0Hydronic)
    impl.sent = []
    impl._send_to = lambda dst, payload, src=None: impl.sent.append((dst.name, payload))
    return impl


def only_event(actor: House0Hydronic) -> tuple[str, FsmEvent]:
    assert len(actor.sent) == 1, actor.sent
    dst, payload = actor.sent[0]
    assert isinstance(payload, FsmEvent)
    return dst, payload


LOOP_METHODS = {
    "sieg_valve_active",
    "sieg_valve_hold",
    "change_to_hp_keep_less",
    "change_to_hp_keep_more",
}


def boss_of(actor: House0Hydronic, method: str):
    """`n` is the boss of every plant relay once the command tree is set,
    except the two loop relays, which sit under sieg-loop when the ops word
    runs the loop (both sim pairs do)."""
    if method in LOOP_METHODS:
        return actor.layout.node("sieg-loop")
    return actor.layout.node(CoreNodeNames.local_control_normal)


# --- choreography -----------------------------------------------------------

CHOREOGRAPHY = [
    # (method, layout attribute of the target, event type, event name)
    (
        "close_tstat_common_relay",
        "tstat_common_relay",
        ChangeRelayState,
        ChangeRelayState.CloseRelay,
    ),
    (
        "open_tstat_common_relay",
        "tstat_common_relay",
        ChangeRelayState,
        ChangeRelayState.OpenRelay,
    ),
    (
        "valved_to_discharge_store",
        "store_charge_discharge_relay",
        ChangeStoreFlowRelay,
        ChangeStoreFlowRelay.DischargeStore,
    ),
    (
        "valved_to_charge_store",
        "store_charge_discharge_relay",
        ChangeStoreFlowRelay,
        ChangeStoreFlowRelay.ChargeStore,
    ),
    (
        "hp_failsafe_switch_to_aquastat",
        "hp_failsafe_relay",
        ChangeHeatPumpControl,
        ChangeHeatPumpControl.SwitchToTankAquastat,
    ),
    (
        "hp_failsafe_switch_to_scada",
        "hp_failsafe_relay",
        ChangeHeatPumpControl,
        ChangeHeatPumpControl.SwitchToScada,
    ),
    (
        "aquastat_ctrl_switch_to_boiler",
        "aquastat_control_relay",
        ChangeAquastatControl,
        ChangeAquastatControl.SwitchToBoiler,
    ),
    (
        "aquastat_ctrl_switch_to_scada",
        "aquastat_control_relay",
        ChangeAquastatControl,
        ChangeAquastatControl.SwitchToScada,
    ),
    (
        "turn_off_store_pump",
        "store_pump_relay",
        ChangeRelayState,
        ChangeRelayState.OpenRelay,
    ),
    (
        "turn_on_store_pump",
        "store_pump_relay",
        ChangeRelayState,
        ChangeRelayState.CloseRelay,
    ),
    (
        "primary_pump_failsafe_to_hp",
        "primary_pump_failsafe",
        ChangePrimaryPumpControl,
        ChangePrimaryPumpControl.SwitchToHeatPump,
    ),
    (
        "primary_pump_failsafe_to_scada",
        "primary_pump_failsafe",
        ChangePrimaryPumpControl,
        ChangePrimaryPumpControl.SwitchToScada,
    ),
    (
        "turn_off_primary_pump",
        "primary_pump_scada_ops",
        ChangeRelayState,
        ChangeRelayState.OpenRelay,
    ),
    (
        "turn_on_primary_pump",
        "primary_pump_scada_ops",
        ChangeRelayState,
        ChangeRelayState.CloseRelay,
    ),
    (
        "sieg_valve_active",
        "hp_loop_on_off",
        ChangeRelayState,
        ChangeRelayState.CloseRelay,
    ),
    ("sieg_valve_hold", "hp_loop_on_off", ChangeRelayState, ChangeRelayState.OpenRelay),
    (
        "change_to_hp_keep_less",
        "hp_loop_keep_send",
        ChangeKeepSend,
        ChangeKeepSend.ChangeToKeepLess,
    ),
    (
        "change_to_hp_keep_more",
        "hp_loop_keep_send",
        ChangeKeepSend,
        ChangeKeepSend.ChangeToKeepMore,
    ),
    ("turn_on_HP", "hp_boss", TurnHpOnOff, TurnHpOnOff.TurnOn),
    ("turn_off_HP", "hp_boss", TurnHpOnOff, TurnHpOnOff.TurnOff),
]


@pytest.mark.parametrize(("method", "target", "event_type", "event_name"), CHOREOGRAPHY)
def test_plant_command_from_the_boss(
    actor: House0Hydronic, method: str, target: str, event_type, event_name
) -> None:
    boss = boss_of(actor, method)
    getattr(actor, method)(boss)
    dst, event = only_event(actor)
    target_node = getattr(actor.layout, target)
    assert dst == target_node.name
    assert event.ToHandle == target_node.handle
    assert event.FromHandle == boss.handle
    assert event.EventType == event_type.enum_name()
    assert event.EventName == event_name


@pytest.mark.parametrize("method", [row[0] for row in CHOREOGRAPHY])
def test_plant_command_sends_nothing_when_not_the_boss(
    actor: House0Hydronic, method: str
) -> None:
    # The local-control node (`auto.lc`) is the boss of `n`, not of the relays,
    # and `n` is not the boss of the loop relays: the FsmEvent fails its boss
    # axiom and the helper logs instead of sending.
    getattr(actor, method)()
    if method in LOOP_METHODS:
        getattr(actor, method)(actor.layout.node(CoreNodeNames.local_control_normal))
    assert actor.sent == []


def test_sieg_loop_node_only_when_the_ops_word_uses_the_loop(
    actor: House0Hydronic, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert actor.data.use_sieg_loop  # both sim pairs run the loop
    assert actor.sieg_loop is actor.layout.node("sieg-loop")
    monkeypatch.setattr(type(actor.data), "use_sieg_loop", property(lambda self: False))
    with pytest.raises(Exception):
        actor.sieg_loop


# --- pure readers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "kwh"),
    [(None, 0.0), (0, 0.0), (12_345, 12.345)],
)
def test_energy_readers_are_kwh_from_wh_and_zero_when_unknown(
    actor: House0Hydronic, raw, kwh: float
) -> None:
    actor.data.latest_channel_values[HCN.usable_energy] = raw
    actor.data.latest_channel_values[HCN.required_energy] = raw
    assert actor.usable_kwh == kwh
    assert actor.required_kwh == kwh
    assert actor.is_storage_empty() is (kwh < 0.2)


def read_now(actor: House0Hydronic, channel_name: str, value: int | None) -> None:
    """A reading of the channel taken now; None is a channel with no reading."""
    actor.data.latest_channel_values[channel_name] = value
    actor.data.latest_channel_unix_ms[channel_name] = (
        None if value is None else int(time.time() * 1000)
    )


def test_total_hp_power_needs_both_units(actor: House0Hydronic) -> None:
    read_now(actor, HCN.hp_idu_pwr, 500)
    read_now(actor, HCN.hp_odu_pwr, None)
    assert actor.total_hp_pwr_w() is None
    read_now(actor, HCN.hp_odu_pwr, 3_000)
    assert actor.total_hp_pwr_w() == 3_500


def test_defrost_is_never_judged_for_a_unit_without_a_known_line(
    actor: House0Hydronic,
) -> None:
    # Both sim pairs name SimHpOdu, which has no defrost signature.
    read_now(actor, HCN.hp_idu_pwr, 100)
    read_now(actor, HCN.hp_odu_pwr, 100)
    assert actor.hp_in_defrost() is False


@pytest.mark.parametrize(
    ("draw", "max_w", "idu", "odu", "defrost"),
    [
        ("total", 8_400, 4_000, 4_399, True),  # LG-shaped: idu + odu under the line
        ("total", 8_400, 4_000, 4_400, False),
        (
            "idu",
            4_000,
            3_999,
            9_000,
            True,
        ),  # Samsung hydro-kit-shaped: idu alone under the line
        ("idu", 4_000, 4_000, 100, False),
    ],
)
def test_defrost_signature_by_the_hp_odu_device_type(
    actor: House0Hydronic,
    monkeypatch: pytest.MonkeyPatch,
    draw: str,
    max_w: int,
    idu: int,
    odu: int,
    defrost: bool,
) -> None:
    device_type = actor.layout.node(HSNN.hp_odu).component.gt.DeviceType
    monkeypatch.setitem(
        house0_module.DEFROST_SIGNATURES,
        device_type,
        house0_module.DefrostSignature(draw, max_w),
    )
    read_now(actor, HCN.hp_idu_pwr, idu)
    read_now(actor, HCN.hp_odu_pwr, odu)
    assert actor.hp_in_defrost() is defrost


def test_defrost_is_false_without_the_watched_draw(
    actor: House0Hydronic, monkeypatch: pytest.MonkeyPatch
) -> None:
    device_type = actor.layout.node(HSNN.hp_odu).component.gt.DeviceType
    monkeypatch.setitem(
        house0_module.DEFROST_SIGNATURES,
        device_type,
        house0_module.DefrostSignature("total", 8_400),
    )
    read_now(actor, HCN.hp_idu_pwr, 100)
    read_now(actor, HCN.hp_odu_pwr, None)
    assert actor.hp_in_defrost() is False


def set_store_relay(actor: House0Hydronic, state: StoreFlowRelay) -> None:
    relay = actor.layout.store_charge_discharge_relay
    actor.data.latest_machine_state[relay.name] = SingleMachineState(
        MachineHandle=relay.handle,
        StateEnum=StoreFlowRelay.enum_name(),
        State=state,
        UnixMs=int(time.time() * 1000),
    )


@pytest.mark.parametrize(
    ("state", "flow_gpm_x100", "expected"),
    [
        (StoreFlowRelay.DischargingStore, 11, True),  # above the 0.1 gpm pump threshold
        (StoreFlowRelay.DischargingStore, 10, False),  # at it: not moving
        (StoreFlowRelay.ChargingStore, 500, False),
        (None, 500, False),  # relay state not yet reported
    ],
)
def test_store_flow_predicates(
    actor: House0Hydronic, state, flow_gpm_x100: int, expected: bool
) -> None:
    if state is not None:
        set_store_relay(actor, state)
    actor.data.latest_channel_values[HCN.store_flow] = flow_gpm_x100
    actor.data.latest_channel_values[HCN.primary_flow] = flow_gpm_x100
    assert actor.discharging_store() is expected
    assert actor.flowing_from_hp_to_house() is expected


# --- the temperature pass ---------------------------------------------------


def f_x100(f: float) -> int:
    """The derived tank/buffer layer channels carry FahrenheitX100."""
    return round(f * 100)


def test_get_temperatures_converts_and_marks_the_buffer_available(
    actor: House0Hydronic,
) -> None:
    buffer = HCN.buffer
    tank = actor.layout.store_tanks[1]
    for ch, f in (
        (buffer.depth1, 150.0),
        (buffer.depth2, 140.0),
        (buffer.depth3, 130.0),
        (tank.depth1, 160.0),
        (tank.depth2, 155.0),
        (tank.depth3, 150.0),
    ):
        actor.data.latest_channel_values[ch] = f_x100(f)
    actor.get_temperatures()
    temps = actor.data.latest_temperatures_f
    assert temps[buffer.depth1] == 150.0 and temps[buffer.depth3] == 130.0
    assert temps[tank.depth1] == 160.0 and temps[tank.depth3] == 150.0
    assert actor.buffer_temps_available is True
    assert list(temps) == sorted(temps)


def test_get_temperatures_buffer_unavailable_when_a_layer_is_missing(
    actor: House0Hydronic,
) -> None:
    buffer = HCN.buffer
    actor.data.latest_channel_values[buffer.depth1] = f_x100(150.0)
    actor.data.latest_channel_values[buffer.depth2] = None
    actor.get_temperatures()
    assert actor.buffer_temps_available is False
    assert (
        buffer.depth2 not in actor.data.latest_temperatures_f
    )  # the buffer is never filled in


def test_missing_store_layers_fill_from_the_layer_below(actor: House0Hydronic) -> None:
    tank = actor.layout.store_tanks[1]
    actor.data.latest_channel_values[tank.depth1] = None  # missing
    actor.data.latest_channel_values[tank.depth2] = f_x100(140.0)
    actor.data.latest_channel_values[tank.depth3] = f_x100(131.0)
    actor.get_temperatures()
    temps = actor.data.latest_temperatures_f
    assert temps[tank.depth1] == 140.0  # stratified: no colder than the layer below
    assert temps[tank.depth2] == 140.0 and temps[tank.depth3] == 131.0


def test_below_floor_store_temp_is_dropped_and_filled_from_the_coldest_layer(
    actor: House0Hydronic,
) -> None:
    tank = actor.layout.store_tanks[1]
    actor.data.latest_channel_values[tank.depth1] = None
    actor.data.latest_channel_values[tank.depth2] = f_x100(140.0)
    actor.data.latest_channel_values[tank.depth3] = f_x100(
        20.0
    )  # below MIN_VALID_TANK_TEMP_F: a fault
    actor.get_temperatures()
    temps = actor.data.latest_temperatures_f
    assert (
        temps[tank.depth3] == 140.0
    )  # no store-cold-pipe in the sim: the coldest reporting layer
    assert temps[tank.depth2] == 140.0
    assert temps[tank.depth1] == 140.0


def test_implausible_store_temp_is_scrubbed_even_when_every_layer_reports(
    actor: House0Hydronic,
) -> None:
    tank = actor.layout.store_tanks[1]
    for ch, f in ((tank.depth1, 250.0), (tank.depth2, 140.0), (tank.depth3, 130.0)):
        actor.data.latest_channel_values[ch] = f_x100(f)
    actor.get_temperatures()
    assert actor.data.latest_temperatures_f[tank.depth1] == 140.0


def test_a_summer_store_at_basement_ambient_is_water(actor: House0Hydronic) -> None:
    """Oak, 2026-09-15: every layer 60-65 F with the heat pump off."""
    tank = actor.layout.store_tanks[1]
    for ch, f in ((tank.depth1, 61.0), (tank.depth2, 61.6), (tank.depth3, 60.2)):
        actor.data.latest_channel_values[ch] = f_x100(f)
    actor.get_temperatures()
    temps = actor.data.latest_temperatures_f
    assert (temps[tank.depth1], temps[tank.depth2], temps[tank.depth3]) == (
        61.0,
        61.6,
        60.2,
    )


def test_a_store_with_no_valid_reading_stays_empty(actor: House0Hydronic) -> None:
    tank = actor.layout.store_tanks[1]
    for ch in (tank.depth1, tank.depth2, tank.depth3):
        actor.data.latest_channel_values[ch] = None
    actor.get_temperatures()
    assert not any(
        ch in actor.data.latest_temperatures_f
        for ch in (tank.depth1, tank.depth2, tank.depth3)
    )


# --- buffer judgment ----------------------------------------------------------
# Every House0 has a buffer tank; what varies is which of its temperature
# channels report. Each predicate walks a fixed preference list, answers from
# the first channel present, and returns False when nothing on its list does.


def set_forecast(
    actor: House0Hydronic, rswt_f: list[float], delta_t_f: list[float]
) -> None:
    n = len(rswt_f)
    actor.data.heating_forecast = HeatingForecast(
        FromGNodeAlias=actor.layout.ltn_g_node_alias,
        Time=[int(time.time()) + 3600 * i for i in range(n)],
        AvgPowerKw=[1.0] * n,
        RswtF=rswt_f,
        RswtDeltaTF=delta_t_f,
        WeatherUid="d5a2b8f6-7c4e-4f1a-9b3d-2e6c8a0f1b47",
    )


def set_temps(actor: House0Hydronic, **temps_f: float) -> None:
    """Channel names are the tier spellings with dashes as underscores."""
    for name, f in temps_f.items():
        actor.data.latest_temperatures_f[name.replace("_", "-")] = f


def set_flowing(actor: House0Hydronic, flowing: bool) -> None:
    """Both flow predicates key on the store relay discharging plus flow above 0.1 gpm."""
    set_store_relay(
        actor,
        StoreFlowRelay.DischargingStore if flowing else StoreFlowRelay.ChargingStore,
    )
    actor.data.latest_channel_values[HCN.store_flow] = 500
    actor.data.latest_channel_values[HCN.primary_flow] = 500


def keep_buffer_full(actor: House0Hydronic, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actor.ops.FamilyParams, "KeepBufferFull", True)


def info_glitches(actor: House0Hydronic) -> list[Glitch]:
    return [p for _, p in actor.sent if isinstance(p, Glitch)]


def test_buffer_empty_is_false_with_no_channel_or_no_forecast(
    actor: House0Hydronic,
) -> None:
    assert actor.is_buffer_empty() is False
    set_temps(actor, buffer_depth1=100.0)
    assert actor.is_buffer_empty() is False  # no forecast: cannot assert empty
    set_forecast(actor, [120.0, 125.0, 130.0, 150.0], [10.0] * 4)
    assert actor.is_buffer_empty() is True  # 100 < max of the first three RswtF (130)


def test_buffer_empty_judges_depth1_against_the_three_hour_rswt(
    actor: House0Hydronic,
) -> None:
    set_forecast(actor, [120.0, 125.0, 130.0, 150.0], [10.0] * 4)
    set_temps(actor, buffer_depth1=130.0)
    assert actor.is_buffer_empty() is False  # at the requirement is not empty
    set_temps(actor, buffer_depth1=129.9)
    assert actor.is_buffer_empty() is True


def test_buffer_empty_threshold_is_capped_ten_under_max_ewt(
    actor: House0Hydronic,
) -> None:
    assert actor.data.ha1_params.MaxEwtF == 170
    set_forecast(actor, [175.0] * 3, [10.0] * 3)
    set_temps(actor, buffer_depth1=160.0)
    assert actor.is_buffer_empty() is False  # threshold is 160, not 175


def test_buffer_empty_falls_through_to_dist_swt(actor: House0Hydronic) -> None:
    set_forecast(actor, [130.0] * 3, [10.0] * 3)
    set_temps(actor, dist_swt=100.0)
    assert actor.is_buffer_empty() is True
    set_temps(actor, buffer_depth1=140.0)  # depth1 wins over the proxy
    assert actor.is_buffer_empty() is False


def test_buffer_empty_short_cycle_ally_uses_depth3_and_the_delta_t(
    actor: House0Hydronic, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_forecast(actor, [130.0] * 3, [10.0] * 3)
    set_temps(actor, buffer_depth1=100.0, buffer_depth3=125.0)
    assert (
        actor.is_buffer_empty(all_tanks_leaf_ally=True) is True
    )  # ops word off: depth1 vs 130
    keep_buffer_full(actor, monkeypatch)
    assert (
        actor.is_buffer_empty(all_tanks_leaf_ally=True) is False
    )  # depth3 125 >= 130 - 10


def test_buffer_full_from_depth3_sends_no_glitch(actor: House0Hydronic) -> None:
    assert actor.is_buffer_full() is False  # nothing reporting
    set_forecast(actor, [130.0] * 3, [10.0] * 3)
    set_temps(actor, buffer_depth3=130.1, buffer_cold_pipe=50.0)
    assert actor.is_buffer_full() is True
    assert info_glitches(actor) == []
    set_temps(actor, buffer_depth3=130.0)
    assert actor.is_buffer_full() is False  # at the requirement is not full


def test_buffer_full_without_forecast_caps_at_max_ewt(actor: House0Hydronic) -> None:
    set_temps(actor, buffer_depth3=170.0)
    assert actor.is_buffer_full() is False
    set_temps(actor, buffer_depth3=170.1)
    assert actor.is_buffer_full() is True


def test_buffer_full_proxies_in_order_and_each_sends_a_glitch(
    actor: House0Hydronic,
) -> None:
    set_forecast(actor, [130.0] * 3, [10.0] * 3)
    set_temps(actor, store_cold_pipe=140.0, hp_ewt=140.0)
    assert actor.is_buffer_full() is False  # neither pipe counts while nothing flows
    set_flowing(actor, True)
    assert actor.is_buffer_full() is True  # store-cold-pipe while discharging the store
    assert HCN.store_cold_pipe in info_glitches(actor)[-1].Details
    set_temps(actor, buffer_cold_pipe=100.0)
    assert actor.is_buffer_full() is False  # buffer-cold-pipe outranks the store pipe
    assert HCN.buffer_cold_pipe in info_glitches(actor)[-1].Details


def test_buffer_full_uses_hp_ewt_only_while_the_heat_pump_feeds_the_house(
    actor: House0Hydronic,
) -> None:
    set_forecast(actor, [130.0] * 3, [10.0] * 3)
    set_temps(actor, hp_ewt=140.0)
    set_flowing(actor, False)
    assert actor.is_buffer_full() is False
    set_flowing(actor, True)
    assert actor.is_buffer_full() is True
    assert HCN.hp_ewt in info_glitches(actor)[-1].Details


def test_buffer_charge_limited_prefers_hp_ewt_while_flowing(
    actor: House0Hydronic,
) -> None:
    assert actor.is_buffer_charge_limited() is False  # nothing reporting
    set_temps(actor, buffer_depth3=170.0)
    assert (
        actor.is_buffer_charge_limited() is True
    )  # depth3 is the last resort; >= MaxEwtF
    set_temps(actor, buffer_cold_pipe=100.0)
    assert actor.is_buffer_charge_limited() is False  # buffer-cold-pipe outranks depth3
    set_temps(actor, hp_ewt=170.0)
    assert actor.is_buffer_charge_limited() is False  # hp-ewt only counts while flowing
    set_flowing(actor, True)
    assert actor.is_buffer_charge_limited() is True


def test_storage_colder_than_buffer_needs_both_tops(actor: House0Hydronic) -> None:
    assert actor.is_storage_colder_than_buffer() is False
    set_temps(actor, buffer_depth1=140.0)
    assert actor.is_storage_colder_than_buffer() is False  # no storage top
    set_temps(actor, tank1_depth1=134.6)
    assert (
        actor.is_storage_colder_than_buffer() is False
    )  # exactly 5.4 colder is not enough
    set_temps(actor, tank1_depth1=134.5)
    assert actor.is_storage_colder_than_buffer() is True
    assert actor.is_storage_colder_than_buffer(min_delta_f=6.0) is False


def test_storage_colder_than_buffer_walks_the_preference_lists(
    actor: House0Hydronic,
) -> None:
    set_temps(actor, buffer_cold_pipe=120.0, buffer_hot_pipe=100.0)
    assert actor.is_storage_colder_than_buffer() is True  # last resorts on both sides
    set_temps(actor, store_hot_pipe=118.0)
    assert (
        actor.is_storage_colder_than_buffer() is False
    )  # store-hot-pipe outranks buffer-hot-pipe
    set_temps(actor, buffer_depth2=130.0)
    assert (
        actor.is_storage_colder_than_buffer() is True
    )  # depth2 outranks the cold pipe
    set_temps(actor, buffer_depth1=120.0)
    assert actor.is_storage_colder_than_buffer() is False  # depth1 outranks depth2


def test_storage_colder_than_buffer_short_cycle_ally_compares_the_buffer_bottom(
    actor: House0Hydronic, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_temps(actor, buffer_depth1=140.0, buffer_depth3=120.0, tank1_depth1=125.0)
    assert (
        actor.is_storage_colder_than_buffer(all_tanks_leaf_ally=True) is True
    )  # ops word off: 140 vs 125
    keep_buffer_full(actor, monkeypatch)
    assert (
        actor.is_storage_colder_than_buffer(all_tanks_leaf_ally=True) is False
    )  # 120 > 125 is false
    set_temps(actor, buffer_depth3=125.1)
    assert (
        actor.is_storage_colder_than_buffer(all_tanks_leaf_ally=True) is True
    )  # no margin
