"""The plant: where a device actor asks for its own device by node name.
It routes to whatever was put behind the node and does nothing else."""

from pathlib import Path
from typing import Iterable, Optional

import pytest
from gwsproto.enums import ChangeRelayPin

from plant import Deliver, Plant, PlantReadings, RelayDrive, SensorSource
from plant_link import (
    PLANT_SILENT_AFTER_S,
    InProcessPlantLink,
    LinkRelayDrive,
    PlantLinkKind,
)
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent / "config"
READ_MS = 1_735_689_600_123
ENERGIZE = ChangeRelayPin.Energize
DE_ENERGIZE = ChangeRelayPin.DeEnergize


class BenchSource(SensorSource):
    """A sensor source that is not the plant link: what a real device's
    half looks like from the plant."""

    def __init__(self) -> None:
        self.deliver_by_channel: dict[str, Deliver] = {}

    def sense(self, channel_names: Iterable[str], deliver: Deliver) -> None:
        for name in channel_names:
            self.deliver_by_channel[name] = deliver

    def read(self, channel_name: str, value: int) -> None:
        self.deliver_by_channel[channel_name](PlantReadings((channel_name,), (value,), READ_MS))


class BenchDrive(RelayDrive):
    """A relay drive that is not the plant link, and can fail."""

    def __init__(self) -> None:
        self.position: Optional[ChangeRelayPin] = None
        self.fault: Optional[str] = None

    async def set(self, action: ChangeRelayPin) -> Optional[str]:
        if self.fault is not None:
            return self.fault
        self.position = action
        return None

    async def read(self) -> Optional[ChangeRelayPin]:
        return self.position


def in_process() -> InProcessPlantLink:
    return InProcessPlantLink(silent_after_s=PLANT_SILENT_AFTER_S, monotonic=lambda: 100.0)


def test_a_sensor_senses_through_the_source_behind_its_node() -> None:
    plant = Plant()
    link = in_process()
    plant.route_sensor("hp-lwt", link)
    got: list[PlantReadings] = []

    plant.sense("hp-lwt", ["hp-lwt"], got.append)
    link.show({"hp-lwt": 5_200}, READ_MS)

    assert got == [PlantReadings(("hp-lwt",), (5_200,), READ_MS)]


def test_a_node_nothing_was_routed_for_cannot_sense_or_be_driven() -> None:
    plant = Plant()
    with pytest.raises(ValueError, match="hp-lwt has no sensor source"):
        plant.sense("hp-lwt", ["hp-lwt"], lambda _readings: None)
    with pytest.raises(ValueError, match="store-pump-relay has no relay drive"):
        plant.relay("store-pump-relay")


def test_a_node_is_routed_once() -> None:
    plant = Plant()
    link = in_process()
    plant.route_sensor("hp-lwt", link)
    plant.route_relay("store-pump-relay", link.drive("store-pump-relay"))
    with pytest.raises(ValueError, match="hp-lwt already has a sensor source"):
        plant.route_sensor("hp-lwt", BenchSource())
    with pytest.raises(ValueError, match="store-pump-relay already has a relay drive"):
        plant.route_relay("store-pump-relay", BenchDrive())


@pytest.mark.asyncio
async def test_a_simulated_relay_takes_every_set_and_reads_what_the_plant_was_told() -> None:
    link = in_process()
    drive = link.drive("store-pump-relay")
    assert await drive.read() is None

    assert await drive.set(ENERGIZE) is None
    assert await drive.read() == ENERGIZE
    assert await drive.set(DE_ENERGIZE) is None
    assert await drive.read() == DE_ENERGIZE

    assert link.actuations == [("store-pump-relay", ENERGIZE), ("store-pump-relay", DE_ENERGIZE)]


@pytest.mark.asyncio
async def test_one_plant_holds_simulated_and_other_devices_side_by_side() -> None:
    """A house with a simulated tank sensor beside a board of its own: each
    node reaches what was put behind it, and neither sees the other's."""
    plant = Plant()
    link = in_process()
    bench_source = BenchSource()
    bench_drive = BenchDrive()
    plant.route_sensor("tank1", link)
    plant.route_sensor("hp-lwt", bench_source)
    plant.route_relay("store-pump-relay", link.drive("store-pump-relay"))
    plant.route_relay("vdc-relay", bench_drive)
    from_link: list[PlantReadings] = []
    from_bench: list[PlantReadings] = []
    plant.sense("tank1", ["tank1-depth1"], from_link.append)
    plant.sense("hp-lwt", ["hp-lwt"], from_bench.append)

    link.show({"tank1-depth1": 4_800}, READ_MS)
    bench_source.read("hp-lwt", 5_200)

    assert from_link == [PlantReadings(("tank1-depth1",), (4_800,), READ_MS)]
    assert from_bench == [PlantReadings(("hp-lwt",), (5_200,), READ_MS)]

    assert await plant.relay("store-pump-relay").set(ENERGIZE) is None
    assert await plant.relay("vdc-relay").set(ENERGIZE) is None
    assert link.actuations == [("store-pump-relay", ENERGIZE)]
    assert await plant.relay("vdc-relay").read() == ENERGIZE

    bench_drive.fault = "expander 0x21 did not answer"
    assert await plant.relay("vdc-relay").set(DE_ENERGIZE) == "expander 0x21 did not answer"
    assert await plant.relay("vdc-relay").read() == ENERGIZE


def app_on(pair: str) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / f"{pair}.layout.json"
    settings.paths.operational_params = CONFIG / f"{pair}.operational.params.json"
    settings.plant_link = PlantLinkKind.InProcess
    settings.paths.mkdirs()
    return ScadaApp(app_settings=settings)


@pytest.mark.parametrize(
    ("pair", "sim_sensors", "relays"),
    [("gw.house0.no.sieg.hazel", 11, 11), ("gw.nolan", 0, 20)],
)
def test_the_app_puts_the_link_behind_sim_sensors_and_simulated_board_relays(
    pair: str, sim_sensors: int, relays: int
) -> None:
    app = app_on(pair)
    link = app.plant_link
    assert isinstance(link, InProcessPlantLink)

    assert len(app.plant.source_by_node) == sim_sensors
    assert all(source is link for source in app.plant.source_by_node.values())
    assert len(app.plant.drive_by_node) == relays
    for name, drive in app.plant.drive_by_node.items():
        assert isinstance(drive, LinkRelayDrive)
        assert (drive.link, drive.relay_name) == (link, name)


@pytest.mark.asyncio
async def test_a_simulated_house_relay_is_driven_through_the_plant_by_its_node_name() -> None:
    app = app_on("gw.house0.no.sieg.hazel")
    link = app.plant_link
    assert isinstance(link, InProcessPlantLink)

    assert await app.plant.relay("store-pump-relay").set(ENERGIZE) is None

    assert link.actuations == [("store-pump-relay", ENERGIZE)]
    assert await app.plant.relay("store-pump-relay").read() == ENERGIZE
    with pytest.raises(ValueError, match="dist-010v has no relay drive"):
        app.plant.relay("dist-010v")


@pytest.mark.asyncio
async def test_the_secondary_scada_has_a_plant_with_nothing_behind_it(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(request=request) as h:
        plant = h.child2_app.plant
        assert plant.source_by_node == {}
        assert plant.drive_by_node == {}
