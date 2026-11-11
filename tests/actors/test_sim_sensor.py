"""SimSensorActor reports what the plant shows it, and nothing of its own."""

from pathlib import Path

import pytest
from gwsproto.named_types import SyncedReadings

from actors.sim_sensor import SimSensorActor
from plant import Plant
from plant_link import InProcessPlantLink, PlantLinkKind
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
PAIR = "gw.house0.no.sieg.hazel"
READ_TIME_MS = 1_794_300_000_000


def hazel_settings():
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / f"{PAIR}.layout.json"
    settings.paths.operational_params = CONFIG / f"{PAIR}.operational.params.json"
    settings.plant_link = PlantLinkKind.InProcess
    settings.paths.mkdirs()
    return settings


@pytest.fixture
def app() -> ScadaApp:
    scada_app = ScadaApp(app_settings=hazel_settings())
    scada_app.instantiate()
    return scada_app


def plant_of(app: ScadaApp) -> InProcessPlantLink:
    plant = app.plant_link
    assert isinstance(plant, InProcessPlantLink)
    return plant


def record_sends(sensor: SimSensorActor) -> list[tuple[str, SyncedReadings]]:
    sent: list[tuple[str, SyncedReadings]] = []
    sensor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def test_a_sim_sensor_posts_what_the_plant_shows_at_the_plants_read_time(app: ScadaApp) -> None:
    sensor = app.get_communicator_as_type("primary-flow", SimSensorActor)
    sent = record_sends(sensor)

    plant_of(app).show({"primary-flow-hz": 1_500_000, "primary-flow": 310}, READ_TIME_MS)

    assert sent == [
        (
            app.scada.name,
            SyncedReadings(
                ChannelNameList=["primary-flow-hz", "primary-flow"],
                ValueList=[1_500_000, 310],
                ScadaReadTimeUnixMs=READ_TIME_MS,
            ),
        )
    ]


def test_a_sim_sensor_feeding_a_derived_channel_posts_to_the_generator_too(app: ScadaApp) -> None:
    sensor = app.get_communicator_as_type("dist-swt", SimSensorActor)
    assert sensor.feeds_derived
    sent = record_sends(sensor)

    plant_of(app).show({"dist-swt": 4_870}, READ_TIME_MS)

    assert [dst for dst, _ in sent] == [app.scada.name, sensor.derived_generator.name]
    assert sent[0][1] == sent[1][1]


def test_a_sim_sensor_hears_only_its_own_channels(app: ScadaApp) -> None:
    hp_lwt = app.get_communicator_as_type("hp-lwt", SimSensorActor)
    hp_ewt = app.get_communicator_as_type("hp-ewt", SimSensorActor)
    lwt_sent = record_sends(hp_lwt)
    ewt_sent = record_sends(hp_ewt)

    plant_of(app).show({"hp-lwt": 5_200}, READ_TIME_MS)

    assert [payload.ChannelNameList for _, payload in lwt_sent] == [["hp-lwt"]]
    assert ewt_sent == []


def test_a_sim_sensor_the_plant_has_nothing_behind_fails_the_boot() -> None:
    scada_app = ScadaApp(app_settings=hazel_settings())
    scada_app._plant = Plant()
    with pytest.raises(ValueError, match="has no device in the plant"):
        scada_app.instantiate()


@pytest.mark.asyncio
async def test_a_running_scada_holds_what_the_plant_shows(request: pytest.FixtureRequest) -> None:
    """The whole path with the test as the plant: the link, the sensor and
    the scada's latest values. Until the plant shows something a sim sensor
    reports nothing, while the power meter beside it already has."""
    async with ScadaLiveTest(request=request, child_app_settings=hazel_settings()) as h:
        h.start_child1()
        app = h.child1_app
        data = app.scada.data
        plant = plant_of(app)
        sim_channels = {
            name
            for c in (app.get_communicator(n) for n in app.get_communicator_names())
            if isinstance(c, SimSensorActor)
            for name in c._channel_names
        }
        assert len(sim_channels) == 14
        await h.await_for(
            lambda: data.latest_power_w is not None,
            "the power meter has reported",
        )
        assert {data.latest_channel_values[name] for name in sim_channels} == {None}

        plant.show({"hp-lwt": 5_200, "store-flow": 250, "store-flow-hz": 1_000_000}, READ_TIME_MS)
        await h.await_for(
            lambda: data.latest_channel_values.get("hp-lwt") == 5_200
            and data.latest_channel_values.get("store-flow") == 250,
            "the scada holds the first values shown",
        )

        plant.show({"hp-lwt": 5_260}, READ_TIME_MS + 5_000)
        await h.await_for(
            lambda: data.latest_channel_values.get("hp-lwt") == 5_260,
            "the scada holds the next value shown",
        )
        assert data.latest_channel_values["store-flow"] == 250
