"""A tank module or BTU meter of the sim word has no pico: the plant shows
its channels and the actor takes each flux that carries one as a post. It
sends what the plant showed, in the channels' own encoding, where a real
pico's readings go, counts the pico heard, and leaves out a channel the
layout disables. A real pico's node has no device in the plant."""

from pathlib import Path
from typing import Any

import pytest

from actors.api_btu_meter import ApiBtuMeter
from actors.api_tank_module import ApiTankModule, microvolts_at_c
from actors.pico_cycler import PicoCycler
from gwsproto.data_classes.components import SimPicoBtuMeterComponent, SimPicoTankModuleComponent
from gwsproto.named_types import SyncedReadings
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames
from plant import SensorSource
from plant_link import InProcessPlantLink, PlantLinkKind
from scada_app import ScadaApp
from tests.actors.test_pico_identity import boot, with_real_pico

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
}
READ_MS = 1_700_000_000_000


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


def make_app(pair_name: str) -> ScadaApp:
    layout, ops = PAIRS[pair_name]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    settings.plant_link = PlantLinkKind.InProcess
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    return make_app(request.param)


def link(app: ScadaApp) -> InProcessPlantLink:
    assert isinstance(app.plant_link, InProcessPlantLink)
    return app.plant_link


def impl(actor) -> ApiTankModule:
    return getattr(actor, "_impl", actor)


def tank_actors(app: ScadaApp) -> list[ApiTankModule]:
    return [
        impl(app.get_communicator(name))
        for name in app.get_communicator_names()
        if isinstance(impl(app.get_communicator(name)), ApiTankModule)
    ]


def capture_sends(actor: Any) -> list[tuple[str, Any]]:
    sent: list[tuple[str, Any]] = []
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def test_a_sim_tank_sends_what_the_plant_shows_where_a_picos_readings_go(app: ScadaApp) -> None:
    actors = tank_actors(app)
    assert actors, "no ApiTankModule actors on this layout"
    for a in actors:
        assert isinstance(a._component, SimPicoTankModuleComponent)
        assert app.plant.device(a.name, SensorSource) is app.plant_link
        channels = a.flatlined_channel_names()
        assert channels, f"{a.name} has no enabled channel"
        shown = {name: 4000 + i for i, name in enumerate(channels)}
        sent = capture_sends(a)
        a.liveness.last_heard = 0.0

        link(app).show(shown, READ_MS)

        assert not a.missing()
        expected = SyncedReadings(
            ChannelNameList=channels,
            ValueList=[shown[name] for name in channels],
            ScadaReadTimeUnixMs=READ_MS,
        )
        assert sent == [
            (a.pico_cycler.name, expected),
            (a.primary_scada.name, expected),
            (a.derived_generator.name, expected),
        ]


def test_a_flux_without_one_depth_is_a_post_without_it(app: ScadaApp) -> None:
    a = tank_actors(app)[0]
    channels = a.flatlined_channel_names()
    left_out = channels[1]
    sent = capture_sends(a)

    link(app).show({name: 4000 for name in channels if name != left_out}, READ_MS)

    assert {tuple(readings.ChannelNameList) for _, readings in sent} == {
        tuple(name for name in channels if name != left_out)
    }


def test_a_flux_with_none_of_its_channels_is_no_post(app: ScadaApp) -> None:
    a = tank_actors(app)[0]
    sent = capture_sends(a)
    a.liveness.last_heard = 0.0

    link(app).show({}, READ_MS)

    assert sent == []
    assert a.missing()


def test_a_sim_tank_leaves_out_a_channel_the_layout_disables() -> None:
    app = make_app("nolan")
    a = app.get_communicator_as_type("fancoil", ApiTankModule)
    assert a is not None
    disabled = "fancoil-depth3-device"
    assert a.layout.channel_disabled(disabled)
    sent = capture_sends(a)

    link(app).show(
        {f"fancoil-depth{depth}-device": 4000 for depth in (1, 2, 3)}, READ_MS
    )

    assert sent, "the enabled depths were not sent"
    for _, readings in sent:
        assert disabled not in readings.ChannelNameList
    assert disabled not in link(app).unsensed_channels


@pytest.fixture
def btu() -> ApiBtuMeter:
    actor = make_app("nolan").get_communicator_as_type("primary-btu", ApiBtuMeter)
    assert actor is not None
    return actor


def test_a_sim_btu_meter_sends_what_the_plant_shows(btu: ApiBtuMeter) -> None:
    assert isinstance(btu._component, SimPicoBtuMeterComponent)
    plant_link = btu.services.plant.device(btu.name, SensorSource)
    assert isinstance(plant_link, InProcessPlantLink)
    shown = {"primary-flow": 410, "hp-lwt": 5100, "hp-ewt": 4600}
    sent = capture_sends(btu)
    btu.liveness.last_heard = 0.0

    plant_link.show(shown, READ_MS)

    assert not btu.missing()
    expected = SyncedReadings(
        ChannelNameList=list(shown),
        ValueList=list(shown.values()),
        ScadaReadTimeUnixMs=READ_MS,
    )
    assert (btu.pico_cycler.name, expected) in sent
    assert (btu.primary_scada.name, expected) in sent
    assert all(payload == expected for _, payload in sent)


def test_pico_cycler_tracks_the_sim_btu_pico(btu: ApiBtuMeter) -> None:
    cycler = btu.services.get_communicator_as_type(HydronicSpaceheatNodeNames.pico_cycler, PicoCycler)
    assert cycler is not None
    assert "sim-primary-btu-pico" in cycler.picos


def test_a_sim_btu_meter_leaves_out_a_channel_the_layout_disables() -> None:
    app = make_app("nolan")
    a = app.get_communicator_as_type("secondary-btu", ApiBtuMeter)
    assert a is not None and a.ct_channel is not None
    disabled = a.ct_channel.Name
    assert a.layout.channel_disabled(disabled)
    sent = capture_sends(a)

    link(app).show({disabled: 12, a.flow_channel.Name: 410}, READ_MS)

    assert sent, "the enabled flow was not sent"
    assert all(readings.ChannelNameList == [a.flow_channel.Name] for _, readings in sent)
    assert disabled not in link(app).unsensed_channels


@pytest.mark.parametrize(
    ("node_name", "uid_field"), [("tank1", "PicoHwUid"), ("primary-btu", "HwUid")]
)
def test_a_real_picos_node_has_no_device_in_the_plant(
    tmp_path: Path, node_name: str, uid_field: str
) -> None:
    pair = PAIRS["nolan"]
    app = boot(tmp_path, pair, with_real_pico(pair, node_name, uid_field))
    with pytest.raises(ValueError, match=f"{node_name} has no device in the plant"):
        app.plant.device(node_name, SensorSource)
    still_simulated = "buffer"
    assert app.plant.device(still_simulated, SensorSource) is app.plant_link

