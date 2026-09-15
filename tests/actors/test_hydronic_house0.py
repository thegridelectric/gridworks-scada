"""The House0 plant surface (`actors/hydronic/house0.py`) on both sim House0
pairs. Choreography: every command lands on the right relay from the boss,
with the right event, and nothing is sent by a caller who is not the boss.
Judgment: the pure readers (energy, power, defrost, store flow) and the
temperature pass (`get_temperatures` + `fill_missing_store_temps`) pinned
on the sim channels."""

import time
from pathlib import Path

import pytest

from actors.hydronic.house0 import House0Hydronic
from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwsproto.enums import (
    ChangeAquastatControl,
    ChangeHeatPumpControl,
    ChangeKeepSend,
    ChangePrimaryPumpControl,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    HpModel,
    StoreFlowRelay,
    TurnHpOnOff,
)
from gwsproto.named_types import FsmEvent, SingleMachineState
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
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
    impl = app.get_communicator(H0N.local_control)._impl
    assert isinstance(impl, House0Hydronic)
    impl.sent = []
    impl._send_to = lambda dst, payload, src=None: impl.sent.append((dst.name, payload))
    return impl


def only_event(actor: House0Hydronic) -> tuple[str, FsmEvent]:
    assert len(actor.sent) == 1, actor.sent
    dst, payload = actor.sent[0]
    assert isinstance(payload, FsmEvent)
    return dst, payload


LOOP_METHODS = {"sieg_valve_active", "sieg_valve_hold", "change_to_hp_keep_less", "change_to_hp_keep_more"}


def boss_of(actor: House0Hydronic, method: str):
    """`n` is the boss of every plant relay once the command tree is set,
    except the two loop relays, which sit under sieg-loop when the ops word
    runs the loop (both sim pairs do)."""
    if method in LOOP_METHODS:
        return actor.layout.node("sieg-loop")
    return actor.layout.node(H0N.local_control_normal)


# --- choreography -----------------------------------------------------------

CHOREOGRAPHY = [
    # (method, layout attribute of the target, event type, event name)
    ("close_tstat_common_relay", "tstat_common_relay", ChangeRelayState, ChangeRelayState.CloseRelay),
    ("open_tstat_common_relay", "tstat_common_relay", ChangeRelayState, ChangeRelayState.OpenRelay),
    ("valved_to_discharge_store", "store_charge_discharge_relay", ChangeStoreFlowRelay, ChangeStoreFlowRelay.DischargeStore),
    ("valved_to_charge_store", "store_charge_discharge_relay", ChangeStoreFlowRelay, ChangeStoreFlowRelay.ChargeStore),
    ("hp_failsafe_switch_to_aquastat", "hp_failsafe_relay", ChangeHeatPumpControl, ChangeHeatPumpControl.SwitchToTankAquastat),
    ("hp_failsafe_switch_to_scada", "hp_failsafe_relay", ChangeHeatPumpControl, ChangeHeatPumpControl.SwitchToScada),
    ("aquastat_ctrl_switch_to_boiler", "aquastat_control_relay", ChangeAquastatControl, ChangeAquastatControl.SwitchToBoiler),
    ("aquastat_ctrl_switch_to_scada", "aquastat_control_relay", ChangeAquastatControl, ChangeAquastatControl.SwitchToScada),
    ("turn_off_store_pump", "store_pump_relay", ChangeRelayState, ChangeRelayState.OpenRelay),
    ("turn_on_store_pump", "store_pump_relay", ChangeRelayState, ChangeRelayState.CloseRelay),
    ("primary_pump_failsafe_to_hp", "primary_pump_failsafe", ChangePrimaryPumpControl, ChangePrimaryPumpControl.SwitchToHeatPump),
    ("primary_pump_failsafe_to_scada", "primary_pump_failsafe", ChangePrimaryPumpControl, ChangePrimaryPumpControl.SwitchToScada),
    ("turn_off_primary_pump", "primary_pump_scada_ops", ChangeRelayState, ChangeRelayState.OpenRelay),
    ("turn_on_primary_pump", "primary_pump_scada_ops", ChangeRelayState, ChangeRelayState.CloseRelay),
    ("sieg_valve_active", "hp_loop_on_off", ChangeRelayState, ChangeRelayState.CloseRelay),
    ("sieg_valve_hold", "hp_loop_on_off", ChangeRelayState, ChangeRelayState.OpenRelay),
    ("change_to_hp_keep_less", "hp_loop_keep_send", ChangeKeepSend, ChangeKeepSend.ChangeToKeepLess),
    ("change_to_hp_keep_more", "hp_loop_keep_send", ChangeKeepSend, ChangeKeepSend.ChangeToKeepMore),
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
def test_plant_command_sends_nothing_when_not_the_boss(actor: House0Hydronic, method: str) -> None:
    # The local-control node (`auto.lc`) is the boss of `n`, not of the relays,
    # and `n` is not the boss of the loop relays: the FsmEvent fails its boss
    # axiom and the helper logs instead of sending.
    getattr(actor, method)()
    if method in LOOP_METHODS:
        getattr(actor, method)(actor.layout.node(H0N.local_control_normal))
    assert actor.sent == []


def test_sieg_loop_node_only_when_the_ops_word_uses_the_loop(actor: House0Hydronic, monkeypatch: pytest.MonkeyPatch) -> None:
    assert actor.data.use_sieg_loop  # both sim pairs run the loop
    assert actor.sieg_loop is actor.layout.node("sieg-loop")
    monkeypatch.setattr(type(actor.data), "use_sieg_loop", property(lambda self: False))
    with pytest.raises(Exception):
        actor.sieg_loop


# --- pure readers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "kwh"), [(None, 0.0), (0, 0.0), (12_345, 12.345)],
)
def test_energy_readers_are_kwh_from_wh_and_zero_when_unknown(actor: House0Hydronic, raw, kwh: float) -> None:
    actor.data.latest_channel_values[H0CN.usable_energy] = raw
    actor.data.latest_channel_values[H0CN.required_energy] = raw
    assert actor.usable_kwh == kwh
    assert actor.required_kwh == kwh
    assert actor.is_storage_empty() is (kwh < 0.2)


def test_total_hp_power_needs_both_units(actor: House0Hydronic) -> None:
    actor.data.latest_channel_values[H0CN.hp_idu_pwr] = 500
    actor.data.latest_channel_values[H0CN.hp_odu_pwr] = None
    assert actor.total_hp_pwr_w() is None
    actor.data.latest_channel_values[H0CN.hp_odu_pwr] = 3_000
    assert actor.total_hp_pwr_w() == 3_500


@pytest.mark.parametrize(
    ("model", "idu", "odu", "defrost"),
    [
        (HpModel.SamsungFiveTonneHydroKit, 3_999, 9_000, True),   # Samsung: IDU under 4 kW
        (HpModel.SamsungFiveTonneHydroKit, 4_000, 100, False),
        (HpModel.SamsungFourTonneHydroKit, 3_999, 9_000, True),
        (HpModel.LgHighTempHydroKitPlusMultiV, 4_000, 4_399, True),  # LG: total under 8.4 kW
        (HpModel.LgHighTempHydroKitPlusMultiV, 4_000, 4_400, False),
    ],
)
def test_defrost_threshold_by_hp_model(
    actor: House0Hydronic, monkeypatch: pytest.MonkeyPatch, model: HpModel, idu: int, odu: int, defrost: bool
) -> None:
    monkeypatch.setattr(actor.settings, "hp_model", model)
    actor.data.latest_channel_values[H0CN.hp_idu_pwr] = idu
    actor.data.latest_channel_values[H0CN.hp_odu_pwr] = odu
    assert actor.hp_in_defrost() is defrost


def test_defrost_is_false_without_both_powers(actor: House0Hydronic) -> None:
    actor.data.latest_channel_values[H0CN.hp_idu_pwr] = 100
    actor.data.latest_channel_values[H0CN.hp_odu_pwr] = None
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
        (StoreFlowRelay.DischargingStore, 11, True),   # above the 0.1 gpm pump threshold
        (StoreFlowRelay.DischargingStore, 10, False),  # at it: not moving
        (StoreFlowRelay.ChargingStore, 500, False),
        (None, 500, False),                            # relay state not yet reported
    ],
)
def test_store_flow_predicates(actor: House0Hydronic, state, flow_gpm_x100: int, expected: bool) -> None:
    if state is not None:
        set_store_relay(actor, state)
    actor.data.latest_channel_values[H0CN.store_flow] = flow_gpm_x100
    actor.data.latest_channel_values[H0CN.primary_flow] = flow_gpm_x100
    assert actor.discharging_store() is expected
    assert actor.flowing_from_hp_to_house() is expected


# --- the temperature pass ---------------------------------------------------


def f_x100(f: float) -> int:
    """The derived tank/buffer layer channels carry FahrenheitX100."""
    return round(f * 100)


def test_get_temperatures_converts_and_marks_the_buffer_available(actor: House0Hydronic) -> None:
    buffer = actor.h0cn.buffer
    tank = actor.h0cn.tank[1]
    for ch, f in ((buffer.depth1, 150.0), (buffer.depth2, 140.0), (buffer.depth3, 130.0),
                  (tank.depth1, 160.0), (tank.depth2, 155.0), (tank.depth3, 150.0)):
        actor.data.latest_channel_values[ch] = f_x100(f)
    actor.get_temperatures()
    temps = actor.data.latest_temperatures_f
    assert temps[buffer.depth1] == 150.0 and temps[buffer.depth3] == 130.0
    assert temps[tank.depth1] == 160.0 and temps[tank.depth3] == 150.0
    assert actor.buffer_temps_available is True
    assert list(temps) == sorted(temps)


def test_get_temperatures_buffer_unavailable_when_a_layer_is_missing(actor: House0Hydronic) -> None:
    buffer = actor.h0cn.buffer
    actor.data.latest_channel_values[buffer.depth1] = f_x100(150.0)
    actor.data.latest_channel_values[buffer.depth2] = None
    actor.get_temperatures()
    assert actor.buffer_temps_available is False
    assert buffer.depth2 not in actor.data.latest_temperatures_f  # the buffer is never filled in


def test_missing_store_layers_fill_from_the_layer_below(actor: House0Hydronic) -> None:
    tank = actor.h0cn.tank[1]
    actor.data.latest_channel_values[tank.depth1] = None            # missing
    actor.data.latest_channel_values[tank.depth2] = f_x100(140.0)
    actor.data.latest_channel_values[tank.depth3] = f_x100(131.0)
    actor.get_temperatures()
    temps = actor.data.latest_temperatures_f
    assert temps[tank.depth1] == 140.0  # stratified: no colder than the layer below
    assert temps[tank.depth2] == 140.0 and temps[tank.depth3] == 131.0


def test_implausible_store_temps_are_dropped_then_filled(actor: House0Hydronic) -> None:
    # The plausibility scrub runs inside the fill pass, so it needs a missing
    # layer to trigger; with every layer reporting, an implausible value stays.
    tank = actor.h0cn.tank[1]
    actor.data.latest_channel_values[tank.depth1] = None
    actor.data.latest_channel_values[tank.depth2] = f_x100(140.0)
    actor.data.latest_channel_values[tank.depth3] = f_x100(40.0)   # below MIN_USED_TANK_TEMP_F
    actor.get_temperatures()
    temps = actor.data.latest_temperatures_f
    assert temps[tank.depth3] == actor.MIN_USED_TANK_TEMP_F  # baseline, no store-cold-pipe in the sim
    assert temps[tank.depth2] == 140.0
    assert temps[tank.depth1] == 140.0


def test_implausible_store_temp_survives_when_every_layer_reports(actor: House0Hydronic) -> None:
    tank = actor.h0cn.tank[1]
    for ch, f in ((tank.depth1, 250.0), (tank.depth2, 140.0), (tank.depth3, 130.0)):
        actor.data.latest_channel_values[ch] = f_x100(f)
    actor.get_temperatures()
    assert actor.data.latest_temperatures_f[tank.depth1] == 250.0  # pins today's gating; see the spoke
