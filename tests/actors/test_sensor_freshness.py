"""The heat pump accessors answer None for a channel whose last reading is
older than the flatline bound, and the defrost question falls back to the
last real reading of the draw it watches."""

import time
from pathlib import Path

import pytest

import actors.hydronic.house0 as house0_module
from actors.hydronic.house0 import House0Hydronic
from actors.scada_data import ScadaData
from actors.sh_node_actor import ShNodeActor
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
WILLOW = ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")
NOLAN = ("gw.nolan.layout.json", "gw.nolan.operational.params.json")
ZONE_TEMP = "zone1-main-temp"
DEFROST_MAX_W = 4_000


def make_app(pair: tuple[str, str]) -> ScadaApp:
    layout, ops = pair
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def local_control(app: ScadaApp) -> ShNodeActor:
    return app.get_communicator(CoreNodeNames.local_control)._impl


def read(data: ScadaData, channel_name: str, value: int, age_periods: float = 0) -> None:
    """A reading of the channel, age_periods capture periods old."""
    period_s = data.capture_seconds(data.layout.data_channels[channel_name])
    data.latest_channel_values[channel_name] = value
    data.latest_channel_unix_ms[channel_name] = int(
        1000 * (time.time() - age_periods * period_s)
    )


def test_power_accessors_are_none_for_a_reading_past_the_flatline_bound() -> None:
    actor = local_control(make_app(WILLOW))
    assert isinstance(actor, House0Hydronic)
    read(actor.data, HCN.hp_idu_pwr, 500)
    read(actor.data, HCN.hp_odu_pwr, 3_000)
    assert actor.hp_odu_pwr_w() == 3_000
    assert actor.hp_idu_pwr_w() == 500
    assert actor.total_hp_pwr_w() == 3_500

    read(actor.data, HCN.hp_odu_pwr, 3_000, age_periods=2.2)
    assert actor.data.latest_channel_values[HCN.hp_odu_pwr] == 3_000
    assert actor.hp_odu_pwr_w() is None
    assert actor.total_hp_pwr_w() is None

    read(actor.data, HCN.hp_odu_pwr, 3_000)
    read(actor.data, HCN.hp_idu_pwr, 500, age_periods=2.2)
    assert actor.hp_idu_pwr_w() is None
    assert actor.total_hp_pwr_w() is None


def test_water_temperature_accessors_are_none_past_the_flatline_bound() -> None:
    actor = local_control(make_app(NOLAN))
    read(actor.data, HCN.hp_lwt, 50_000)
    read(actor.data, HCN.hp_ewt, 40_000)
    assert actor.lwt() is not None
    assert actor.ewt() is not None
    assert actor.lift_f() is not None

    read(actor.data, HCN.hp_lwt, 50_000, age_periods=2.2)
    assert actor.lwt() is None
    assert actor.lift_f() is None

    read(actor.data, HCN.hp_lwt, 50_000)
    read(actor.data, HCN.hp_ewt, 40_000, age_periods=2.2)
    assert actor.ewt() is None
    assert actor.lift_f() is None


def test_water_temperature_accessors_on_a_layout_without_the_channels() -> None:
    actor = local_control(make_app(WILLOW))
    assert HCN.hp_lwt not in actor.layout.data_channels
    assert actor.lwt() is None
    assert actor.ewt() is None
    assert actor.lift_f() is None


@pytest.fixture
def defrost_actors(monkeypatch: pytest.MonkeyPatch) -> tuple[House0Hydronic, House0Hydronic]:
    """Local control and the leaf ally of one willow scada, whose sim heat
    pump is given an idu defrost signature."""
    app = make_app(WILLOW)
    lc = local_control(app)
    la = app.get_communicator(CoreNodeNames.leaf_ally)._impl
    assert isinstance(lc, House0Hydronic)
    assert isinstance(la, House0Hydronic)
    assert lc.data is la.data
    monkeypatch.setitem(
        house0_module.DEFROST_SIGNATURES,
        lc.layout.node(HSNN.hp_odu).component.gt.DeviceType,
        house0_module.DefrostSignature("idu", DEFROST_MAX_W),
    )
    return lc, la


def both(actors: tuple[House0Hydronic, House0Hydronic]) -> set[bool]:
    return {actor.hp_in_defrost() for actor in actors}


def test_defrost_holds_on_the_last_real_reading_after_a_flush(
    defrost_actors: tuple[House0Hydronic, House0Hydronic],
) -> None:
    data = defrost_actors[0].data
    # Nobody asks while the reading is live.
    read(data, HCN.hp_idu_pwr, DEFROST_MAX_W - 1)
    data.flush_channel_from_latest(HCN.hp_idu_pwr)
    assert both(defrost_actors) == {True}


def test_defrost_holds_on_the_last_real_reading_flatlined_by_age(
    defrost_actors: tuple[House0Hydronic, House0Hydronic],
) -> None:
    data = defrost_actors[0].data
    read(data, HCN.hp_idu_pwr, DEFROST_MAX_W - 1, age_periods=2.2)
    assert defrost_actors[0].hp_idu_pwr_w() is None
    assert both(defrost_actors) == {True}


def test_no_defrost_when_the_last_real_reading_was_over_the_line(
    defrost_actors: tuple[House0Hydronic, House0Hydronic],
) -> None:
    data = defrost_actors[0].data
    read(data, HCN.hp_idu_pwr, DEFROST_MAX_W)
    data.flush_channel_from_latest(HCN.hp_idu_pwr)
    assert both(defrost_actors) == {False}


def test_no_defrost_for_a_draw_never_read(
    defrost_actors: tuple[House0Hydronic, House0Hydronic],
) -> None:
    data = defrost_actors[0].data
    data.flush_channel_from_latest(HCN.hp_idu_pwr)
    assert both(defrost_actors) == {False}


def test_a_live_reading_answers_again_after_a_loss(
    defrost_actors: tuple[House0Hydronic, House0Hydronic],
) -> None:
    data = defrost_actors[0].data
    read(data, HCN.hp_idu_pwr, DEFROST_MAX_W - 1)
    data.flush_channel_from_latest(HCN.hp_idu_pwr)
    assert both(defrost_actors) == {True}
    read(data, HCN.hp_idu_pwr, DEFROST_MAX_W + 1_000)
    assert both(defrost_actors) == {False}


def test_a_zone_temperature_of_the_same_age_still_comes_back() -> None:
    actor = local_control(make_app(WILLOW))
    read(actor.data, ZONE_TEMP, 20_000, age_periods=2.2)
    assert actor.channel_temperature(ZONE_TEMP) is not None
