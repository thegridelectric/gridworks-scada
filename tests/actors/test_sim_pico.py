"""A simulated tank pico posts, dies, and reboots on the sim component's
script (SimLifeS / SimRebootS), so the pico-cycler loop can be exercised
on a simulated layout.

The source is pure: every method takes the current time, so these tests
drive it with explicit instants and no clock patching. The actor half
checks that ApiTankModule builds a source from the sim word and feeds it the vdc relay's state from the scada's latest
machine states."""

from pathlib import Path

import pytest

from actors.api_btu_meter import SIM_LOOP_CELSIUS_X100, SIM_LOOP_GPM_X100, ApiBtuMeter
from actors.api_tank_module import (
    SIM_TANK_AT_REST_C,
    ApiTankModule,
    microvolts_at_c,
    microvolts_without,
)
from actors.pico_cycler import PicoCycler
from actors.sim_pico_source import SimPicoSource
from gwsproto.data_classes.components import SimPicoBtuMeterComponent, SimPicoTankModuleComponent
from gwsproto.enums import RelayClosedOrOpen
from gwsproto.named_types import MicroVolts, MultichannelSnapshot, SingleMachineState, SyncedReadings
from gwproto import Message
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
}
PERIOD = 60
ABOUT = ["buffer-depth1", "buffer-depth2", "buffer-depth3"]
UV = [1_000_000, 1_100_000, 1_200_000]


def source(life_s=None, reboot_s=None, booted_at=0.0) -> SimPicoSource[MicroVolts]:
    return SimPicoSource(
        reading=MicroVolts(HwUid="sim-buffer-pico", AboutNodeNameList=ABOUT, MicroVoltsList=UV),
        without=microvolts_without,
        capture_period_s=PERIOD,
        life_s=life_s,
        reboot_s=reboot_s,
        booted_at=booted_at,
    )


def posts(src: SimPicoSource[MicroVolts], instants: list[float]) -> list[float]:
    """The instants at which ticking at each instant produced a reading."""
    return [t for t in instants if src.tick(t) is not None]


def test_posts_at_the_capture_period() -> None:
    src = source()
    reading = src.tick(0.0)
    assert isinstance(reading, MicroVolts)
    assert reading.HwUid == "sim-buffer-pico"
    assert reading.AboutNodeNameList == ABOUT
    assert reading.MicroVoltsList == UV
    assert posts(src, [1.0, 30.0, 59.0, 60.0, 61.0, 119.0, 120.0]) == [60.0, 120.0]


def test_a_post_drops_the_omitted_names_until_they_are_cleared() -> None:
    src = source()
    src.omitted_names = {ABOUT[1]}
    reading = src.tick(0.0)
    assert reading is not None
    assert reading.AboutNodeNameList == [ABOUT[0], ABOUT[2]]
    assert reading.MicroVoltsList == [UV[0], UV[2]]
    src.omitted_names = set()
    assert src.tick(float(PERIOD)) == src.reading


def test_no_life_means_it_never_dies() -> None:
    src = source()
    assert posts(src, [float(t) for t in range(0, 24 * 3600, PERIOD)]) == [
        float(t) for t in range(0, 24 * 3600, PERIOD)
    ]


def test_goes_silent_after_sim_life() -> None:
    src = source(life_s=150)
    assert posts(src, [0.0, 60.0, 120.0, 150.0, 180.0, 3600.0]) == [0.0, 60.0, 120.0]
    assert not src.alive


def test_dead_pico_stays_dead_without_reboot() -> None:
    src = source(life_s=10)
    assert posts(src, [0.0, 10.0]) == [0.0]
    src.relay_state(RelayClosedOrOpen.RelayOpen, 20.0)
    src.relay_state(RelayClosedOrOpen.RelayClosed, 25.0)
    assert posts(src, [30.0, 300.0, 3000.0]) == []


def test_reboots_after_relay_closes_following_an_open() -> None:
    src = source(life_s=10, reboot_s=15)
    assert posts(src, [0.0, 10.0]) == [0.0]
    src.relay_state(RelayClosedOrOpen.RelayOpen, 20.0)
    src.relay_state(RelayClosedOrOpen.RelayClosed, 25.0)
    # boots at 40; the life clock restarts from the boot
    assert posts(src, [30.0, 39.0, 40.0, 45.0, 49.0, 50.0]) == [40.0]
    assert not src.alive


def test_relay_open_kills_a_living_pico() -> None:
    src = source(reboot_s=5)
    assert posts(src, [0.0]) == [0.0]
    src.relay_state(RelayClosedOrOpen.RelayOpen, 1.0)
    assert posts(src, [60.0, 120.0]) == []
    src.relay_state(RelayClosedOrOpen.RelayClosed, 130.0)
    assert posts(src, [134.0, 135.0, 194.0, 195.0]) == [135.0, 195.0]


def test_a_close_with_no_prior_open_schedules_nothing() -> None:
    src = source(life_s=10, reboot_s=5)
    assert posts(src, [0.0, 10.0]) == [0.0]
    src.relay_state(RelayClosedOrOpen.RelayClosed, 20.0)
    assert posts(src, [25.0, 100.0]) == []


def test_microvolts_round_trip_through_simple_beta() -> None:
    beta = 3977
    uv = microvolts_at_c(50.0, beta)
    assert 0 < uv < 3_300_000
    # inverse of ApiTankModule.simple_beta, without an actor
    from actors.api_tank_module import PICO_VOLTS, R_FIXED_KOHMS, THERMISTOR_R0_KOHMS, THERMISTOR_T0
    import math

    volts = uv / 1e6
    r_therm = R_FIXED_KOHMS * volts / (PICO_VOLTS - volts)
    temp_c = 1 / ((1 / THERMISTOR_T0) + (math.log(r_therm / THERMISTOR_R0_KOHMS) / beta)) - 273
    assert abs(temp_c - 50.0) < 0.05


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def tank_actors(app: ScadaApp) -> list[ApiTankModule]:
    return [
        impl(app.get_communicator(name))
        for name in app.get_communicator_names()
        if isinstance(impl(app.get_communicator(name)), ApiTankModule)
    ]


def impl(actor) -> ApiTankModule:
    return getattr(actor, "_impl", actor)


def test_sim_tank_actors_carry_a_source(app: ScadaApp) -> None:
    actors = tank_actors(app)
    assert actors, "no ApiTankModule actors on this layout"
    for a in actors:
        assert isinstance(a._component, SimPicoTankModuleComponent)
        assert a.sim_pico is not None
        assert a.sim_pico.reading.HwUid == a._component.gt.PicoHwUid
        assert a.sim_pico.capture_period_s == a.liveness.expected_post_s
        assert a.sim_pico.reading.AboutNodeNameList == [a.depth_about_nodes[d] for d in (1, 2, 3)]
        assert a.sim_pico.reading.MicroVoltsList == [
            microvolts_at_c(SIM_TANK_AT_REST_C[d], a._component.gt.ThermistorBeta) for d in (1, 2, 3)
        ]
        assert a.sim_pico.life_s == a._component.gt.SimLifeS
        assert a.sim_pico.reboot_s == a._component.gt.SimRebootS


def test_actor_feeds_relay_state_from_latest_machine_states(app: ScadaApp) -> None:
    a = tank_actors(app)[0]
    assert a.sim_pico is not None
    a.sim_pico.reboot_s = 5
    vdc = a.layout.nodes[HydronicSpaceheatNodeNames.vdc_relay]

    def relay(state: RelayClosedOrOpen, unix_ms: int) -> None:
        app.scada.data.latest_machine_state[HydronicSpaceheatNodeNames.vdc_relay] = SingleMachineState(
            MachineHandle=vdc.handle,
            StateEnum=RelayClosedOrOpen.enum_name(),
            State=state.value,
            UnixMs=unix_ms,
        )

    a.feed_sim_relay_state(1.0)  # nothing recorded yet: no-op
    relay(RelayClosedOrOpen.RelayOpen, 1_700_000_001_000)
    a.feed_sim_relay_state(1.0)
    assert not a.sim_pico.alive
    a.feed_sim_relay_state(2.0)  # same record, fed once
    relay(RelayClosedOrOpen.RelayClosed, 1_700_000_003_000)
    a.feed_sim_relay_state(3.0)
    assert a.sim_pico.reboot_at == 8.0


# --- the BTU meter over the sim word ------------------------------------------


@pytest.fixture
def btu() -> ApiBtuMeter:
    """The Nolan pair's primary-btu. Sends are captured, not delivered."""
    layout_name, ops_name = PAIRS["nolan"]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout_name
    settings.paths.operational_params = CONFIG / ops_name
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    actor = app.get_communicator_as_type("primary-btu", ApiBtuMeter)
    assert actor is not None
    actor.sent = []
    actor._send_to = lambda dst, payload, src=None: actor.sent.append(payload)
    return actor


def test_sim_btu_actor_carries_a_source(btu: ApiBtuMeter) -> None:
    assert isinstance(btu._component, SimPicoBtuMeterComponent)
    assert btu.sim_pico is not None
    reading = btu.sim_pico.reading
    assert reading.HwUid == btu._component.gt.HwUid
    assert reading.ChannelNameList == ["primary-flow", "hp-lwt", "hp-ewt"]
    assert reading.MeasurementList == [SIM_LOOP_GPM_X100, SIM_LOOP_CELSIUS_X100, SIM_LOOP_CELSIUS_X100]
    assert btu.sim_pico.capture_period_s == btu.liveness.expected_post_s
    assert btu.sim_pico.life_s == btu._component.gt.SimLifeS
    assert btu.sim_pico.reboot_s == btu._component.gt.SimRebootS


def test_sim_btu_reading_goes_out_on_the_real_path(btu: ApiBtuMeter) -> None:
    """The source's snapshot, processed the way a real pico's post is, marks
    the pico heard and sends readings in each channel's declared encoding."""
    assert btu.sim_pico is not None
    reading = btu.sim_pico.tick(0.0)
    assert isinstance(reading, MultichannelSnapshot)

    btu.process_message(Message(Src=btu.name, Dst=btu.name, Payload=reading))

    assert not btu.missing()
    sent = next(p for p in btu.sent if isinstance(p, SyncedReadings))
    registry = btu.layout.channel_registry
    assert sent.ValueList[0] == SIM_LOOP_GPM_X100
    assert registry.temperature("hp-lwt", sent.ValueList[1]).f == pytest.approx(122.0)
    assert registry.temperature("hp-ewt", sent.ValueList[2]).f == pytest.approx(122.0)


def test_pico_cycler_tracks_the_sim_btu_pico(btu: ApiBtuMeter) -> None:
    cycler = btu.services.get_communicator_as_type(HydronicSpaceheatNodeNames.pico_cycler, PicoCycler)
    assert cycler is not None
    assert "sim-primary-btu-pico" in cycler.picos


def test_sim_btu_with_a_ct_posts_its_ct_channel() -> None:
    layout_name, ops_name = PAIRS["nolan"]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout_name
    settings.paths.operational_params = CONFIG / ops_name
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    meters = [
        app.get_communicator_as_type(n.name, ApiBtuMeter)
        for n in app.hardware_layout.nodes.values()
        if n.actor_class == "ApiBtuMeter"
    ]
    with_ct = [a for a in meters if a is not None and a.ct_channel is not None]
    assert with_ct, "no sim BTU meter with a CT on the Nolan pair"
    for a in with_ct:
        assert a.sim_pico is not None
        assert a.ct_channel.Name in a.sim_pico.reading.ChannelNameList
