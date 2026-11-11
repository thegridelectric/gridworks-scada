"""The plant: where a device actor asks for its own device by node name.
It routes to whatever was put behind the node and does nothing else."""

from pathlib import Path
from typing import Iterable, Optional

import pytest
from gwsproto.enums import ChangeRelayPin

from plant import Deliver, Plant, PlantReadings, RelayDrive, RelayRead, SensorSource
from plant_link import (
    PLANT_SILENT_AFTER_S,
    InProcessPlantLink,
    LinkRelayDrive,
    PlantLinkKind,
)
from relay_drives import GpioRelayDrive, I2cRelayDrive
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

    @property
    def reads_back(self) -> bool:
        return True

    async def set(self, action: ChangeRelayPin) -> Optional[str]:
        if self.fault is not None:
            return self.fault
        self.position = action
        return None

    async def read(self) -> RelayRead:
        return RelayRead(self.position, None)


def in_process() -> InProcessPlantLink:
    return InProcessPlantLink(silent_after_s=PLANT_SILENT_AFTER_S, monotonic=lambda: 100.0)


def test_a_sensor_senses_through_the_source_behind_its_node() -> None:
    plant = Plant()
    link = in_process()
    plant.route("hp-lwt", link)
    got: list[PlantReadings] = []

    plant.device("hp-lwt", SensorSource).sense(["hp-lwt"], got.append)
    link.show({"hp-lwt": 5_200}, READ_MS)

    assert got == [PlantReadings(("hp-lwt",), (5_200,), READ_MS)]


def test_a_node_nothing_was_routed_for_cannot_sense_or_be_driven() -> None:
    plant = Plant()
    with pytest.raises(ValueError, match="hp-lwt has no device in the plant"):
        plant.device("hp-lwt", SensorSource)
    plant.route("hp-lwt", in_process())
    with pytest.raises(ValueError, match="hp-lwt has a InProcessPlantLink in the plant, which is no RelayDrive"):
        plant.device("hp-lwt", RelayDrive)


def test_a_node_is_routed_once() -> None:
    plant = Plant()
    link = in_process()
    plant.route("hp-lwt", link)
    plant.route("store-pump-relay", link.drive("store-pump-relay", reads_back=False))
    with pytest.raises(ValueError, match="hp-lwt already has a device"):
        plant.route("hp-lwt", BenchSource())
    with pytest.raises(ValueError, match="store-pump-relay already has a device"):
        plant.route("store-pump-relay", BenchDrive())


@pytest.mark.asyncio
async def test_a_simulated_relay_takes_every_set_and_reads_what_the_plant_was_told() -> None:
    link = in_process()
    drive = link.drive("store-pump-relay", reads_back=True)
    assert await drive.read() == RelayRead(DE_ENERGIZE, None)
    assert await drive.told() == DE_ENERGIZE

    assert await drive.set(ENERGIZE) is None
    assert await drive.read() == RelayRead(ENERGIZE, None)
    assert await drive.told() == ENERGIZE
    assert await drive.set(DE_ENERGIZE) is None
    assert await drive.read() == RelayRead(DE_ENERGIZE, None)

    assert link.actuations == [("store-pump-relay", ENERGIZE), ("store-pump-relay", DE_ENERGIZE)]


@pytest.mark.asyncio
async def test_a_drive_hands_back_what_its_device_throws_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeadGpio:
        HIGH, LOW = 1, 0

        def output(self, pin: int, level: int) -> None:
            raise RuntimeError("the channel is not set up as an OUTPUT")

    on_pin = GpioRelayDrive(22)
    on_pin.gpio = DeadGpio()
    error = await on_pin.set(ENERGIZE)
    assert error is not None
    assert "GPIO 22" in error and "not set up as an OUTPUT" in error

    link = in_process()

    def unplugged(_relay_name: str, _action: ChangeRelayPin) -> None:
        raise OSError("plant unplugged")

    monkeypatch.setattr(link, "actuate", unplugged)
    on_link = link.drive("store-pump-relay", reads_back=True)
    error = await on_link.set(ENERGIZE)
    assert error is not None and "plant unplugged" in error
    assert await on_link.told() == ENERGIZE, "kept, so the link restates it"


@pytest.mark.asyncio
async def test_one_plant_holds_simulated_and_other_devices_side_by_side() -> None:
    """A house with a simulated tank sensor beside a board of its own: each
    node reaches what was put behind it, and neither sees the other's."""
    plant = Plant()
    link = in_process()
    bench_source = BenchSource()
    bench_drive = BenchDrive()
    plant.route("tank1", link)
    plant.route("hp-lwt", bench_source)
    plant.route("store-pump-relay", link.drive("store-pump-relay", reads_back=False))
    plant.route("vdc-relay", bench_drive)
    from_link: list[PlantReadings] = []
    from_bench: list[PlantReadings] = []
    plant.device("tank1", SensorSource).sense(["tank1-depth1"], from_link.append)
    plant.device("hp-lwt", SensorSource).sense(["hp-lwt"], from_bench.append)

    link.show({"tank1-depth1": 4_800}, READ_MS)
    bench_source.read("hp-lwt", 5_200)

    assert from_link == [PlantReadings(("tank1-depth1",), (4_800,), READ_MS)]
    assert from_bench == [PlantReadings(("hp-lwt",), (5_200,), READ_MS)]

    assert await plant.device("store-pump-relay", RelayDrive).set(ENERGIZE) is None
    assert await plant.device("vdc-relay", RelayDrive).set(ENERGIZE) is None
    assert link.actuations == [("store-pump-relay", ENERGIZE)]
    assert await plant.device("vdc-relay", RelayDrive).read() == RelayRead(ENERGIZE, None)

    bench_drive.fault = "expander 0x21 did not answer"
    assert await plant.device("vdc-relay", RelayDrive).set(DE_ENERGIZE) == "expander 0x21 did not answer"
    assert await plant.device("vdc-relay", RelayDrive).read() == RelayRead(ENERGIZE, None)


def app_on(pair: str, layout: Optional[Path] = None) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout or CONFIG / f"{pair}.layout.json"
    settings.paths.operational_params = CONFIG / f"{pair}.operational.params.json"
    settings.plant_link = PlantLinkKind.InProcess
    settings.paths.mkdirs()
    return ScadaApp(app_settings=settings)


@pytest.mark.parametrize(
    ("pair", "sim_sensors", "relays", "reading_back"),
    [("gw.house0.no.sieg.hazel", 11, 11, 0), ("gw.nolan", 0, 20, 19)],
)
def test_the_app_puts_the_link_behind_sim_sensors_and_simulated_board_relays(
    pair: str, sim_sensors: int, relays: int, reading_back: int
) -> None:
    """A simulated relay reads back where its board does: the Krida board
    reads no pin, and the gw108 reads its expander pins and not its one
    GPIO relay."""
    app = app_on(pair)
    link = app.plant_link
    assert isinstance(link, InProcessPlantLink)

    devices = app.plant.device_by_node
    assert sum(device is link for device in devices.values()) == sim_sensors
    drives = {n: d for n, d in devices.items() if isinstance(d, LinkRelayDrive)}
    assert len(drives) == relays
    for name, drive in drives.items():
        assert (drive.link, drive.relay_name) == (link, name)
    assert sum(d.reads_back for d in drives.values()) == reading_back


@pytest.mark.parametrize(
    ("pair", "sim_board", "board", "on_expanders", "on_gpio"),
    [
        ("gw.house0.no.sieg.hazel", "SimKridaDoubleRelayBoard16", "KridaDoubleRelayBoard16", 11, 0),
        ("gw.nolan", "SimGw108", "Gw108RevB", 19, 1),
    ],
)
def test_the_app_puts_the_board_behind_the_relays_of_a_board_that_is_not_simulated(
    tmp_path: Path, pair: str, sim_board: str, board: str, on_expanders: int, on_gpio: int
) -> None:
    layout = tmp_path / "layout.json"
    layout.write_text(
        (CONFIG / f"{pair}.layout.json").read_text().replace(f'"{sim_board}"', f'"{board}"')
    )
    drives = [
        d for d in app_on(pair, layout).plant.device_by_node.values() if isinstance(d, RelayDrive)
    ]

    assert sum(isinstance(d, I2cRelayDrive) for d in drives) == on_expanders
    assert sum(isinstance(d, GpioRelayDrive) for d in drives) == on_gpio
    assert len(drives) == on_expanders + on_gpio


@pytest.mark.asyncio
async def test_a_simulated_house_relay_is_driven_through_the_plant_by_its_node_name() -> None:
    app = app_on("gw.house0.no.sieg.hazel")
    link = app.plant_link
    assert isinstance(link, InProcessPlantLink)

    assert await app.plant.device("store-pump-relay", RelayDrive).set(ENERGIZE) is None

    assert link.actuations == [("store-pump-relay", ENERGIZE)]
    assert await app.plant.device("store-pump-relay", RelayDrive).read() == RelayRead(ENERGIZE, None)
    with pytest.raises(ValueError, match="dist-010v has a KeptLevelDrive in the plant, which is no RelayDrive"):
        app.plant.device("dist-010v", RelayDrive)


@pytest.mark.asyncio
async def test_the_secondary_scada_has_a_plant_with_nothing_behind_it(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(request=request) as h:
        plant = h.child2_app.plant
        assert plant.device_by_node == {}
