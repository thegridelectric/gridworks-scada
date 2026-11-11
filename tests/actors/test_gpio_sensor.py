"""A GPIO sensor publishes its first reading whatever the pin reads, so a
zone already calling when the scada boots is seen at boot. A pin that
cannot be read is a glitch and a gap in the channel, never a stale value."""

import asyncio
from pathlib import Path

import pytest

from actors.gpio_sensor import GpioSensor
from gwsproto.named_types import Glitch, SingleReading
from pin_inputs import GpioPinInput
from plant import PinInput, PinRead
from plant_link import InProcessPlantLink, LinkPinInput, PlantLinkKind
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
OPTO = "zone1-bedrooms-opto"
OPTO_INPUT = "zone1-bedrooms-opto-input"
HEAT_CALL = "zone1-bedrooms-heat-call"
READ_MS = 1_735_689_600_123
OPTO_BCM_PIN = 17


def boot(layout: Path = CONFIG / "gw.nolan.layout.json") -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.plant_link = PlantLinkKind.InProcess
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def the_link(app: ScadaApp) -> InProcessPlantLink:
    link = app.plant_link
    assert isinstance(link, InProcessPlantLink)
    return link


class BenchPin(PinInput):
    """A pin the test holds: a level, or a read that fails."""

    def __init__(self) -> None:
        self.reads = PinRead(None, ())

    def read(self) -> PinRead:
        return self.reads


def sensor_on(pin: PinInput) -> GpioSensor:
    app = boot()
    del app.plant.device_by_node[OPTO]
    app.plant.route(OPTO, pin)
    sensor = GpioSensor(OPTO, app)
    sensor.sent = []
    sensor._send_to = lambda dst, payload, src=None: sensor.sent.append(payload)
    return sensor


@pytest.mark.asyncio
@pytest.mark.parametrize("pin_reads", [0, 1])
async def test_first_reading_publishes_whatever_the_pin_reads(pin_reads: int) -> None:
    app = boot()
    sensor = app.get_communicator_as_type(OPTO, GpioSensor)
    assert sensor is not None
    the_link(app).show({OPTO_INPUT: pin_reads}, READ_MS)
    sent: list[tuple[str, SingleReading]] = []
    sensor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    sensor._send = lambda message: None

    task = asyncio.create_task(sensor.main())
    await asyncio.sleep(0.05)
    sensor._stop_requested = True
    task.cancel()

    assert sensor.send_to_derived
    assert {dst for dst, _ in sent} == {sensor.primary_scada.name, sensor.derived_generator.name}
    assert all(p.ChannelName == sensor.channel_name and p.Value == pin_reads for _, p in sent)
    assert len(sent) == 2


def test_nothing_publishes_before_the_pin_is_read() -> None:
    sensor = boot().get_communicator_as_type(OPTO, GpioSensor)
    assert sensor is not None
    sent: list = []
    sensor._send_to = lambda dst, payload, src=None: sent.append(payload)
    sensor._publish()
    assert sent == []


def test_a_pin_the_plant_has_not_sent_reads_as_nothing_and_says_nothing() -> None:
    app = boot()
    pin = app.plant.device(OPTO, PinInput)
    assert isinstance(pin, LinkPinInput)

    assert pin.read() == PinRead(None, ())
    the_link(app).show({OPTO_INPUT: 0}, READ_MS)
    assert pin.read() == PinRead(0, ())


def test_a_pin_whose_plant_went_silent_fails_its_read_until_the_plant_is_back() -> None:
    app = boot()
    link = the_link(app)
    now = [0.0]
    link.monotonic = lambda: now[0]
    link.born_at = 0.0
    pin = app.plant.device(OPTO, PinInput)

    now[0] = link.silent_after_s + 1
    never_heard = pin.read()
    assert never_heard.value is None
    assert [(s.summary, s.details, s.streak) for s in never_heard.said] == [
        ("gpio-read-failed", "the plant is silent", True)
    ]

    link.show({OPTO_INPUT: 1}, READ_MS)
    assert pin.read() == PinRead(1, ())
    now[0] += link.silent_after_s + 1
    assert pin.read().value is None
    link.show({OPTO_INPUT: 0}, READ_MS)
    assert pin.read() == PinRead(0, ())


def test_a_failed_read_is_one_glitch_a_streak_and_leaves_nothing_to_publish() -> None:
    pin = BenchPin()
    sensor = sensor_on(pin)
    pin.reads = PinRead(1, ())
    assert sensor.read_pin()
    sensor._publish()
    published = len(sensor.sent)
    assert published > 0

    failing = GpioPinInput(OPTO_BCM_PIN)
    pin.reads = failing.read()
    for _ in range(3):
        assert not sensor.read_pin()
        sensor._publish()
    glitches = [p for p in sensor.sent if isinstance(p, Glitch)]
    assert [(g.Summary, g.Details) for g in glitches] == [
        (
            "gpio-read-failed",
            f"{OPTO_INPUT}: GPIO {OPTO_BCM_PIN} read raised "
            "AttributeError(\"'NoneType' object has no attribute 'input'\")",
        )
    ]
    assert sensor.latest_value is None
    assert len(sensor.sent) == published + 1

    pin.reads = PinRead(1, ())
    assert sensor.read_pin(), "the first value after the outage is a change"
    pin.reads = failing.read()
    assert not sensor.read_pin()
    assert len([p for p in sensor.sent if isinstance(p, Glitch)]) == 2, "a new streak"


def test_a_board_pin_reads_its_level_and_hands_back_what_the_pin_throws() -> None:
    class Gpio:
        level = 1

        def input(self, bcm_pin: int) -> int:
            if self.level < 0:
                raise RuntimeError("no access to /dev/mem")
            return self.level

    pin = GpioPinInput(OPTO_BCM_PIN)
    pin.gpio = Gpio()

    assert pin.read() == PinRead(1, ())
    pin.gpio.level = 0
    assert pin.read() == PinRead(0, ())
    pin.gpio.level = -1
    read = pin.read()
    assert read.value is None
    assert [(s.summary, s.details) for s in read.said] == [
        ("gpio-read-failed", f"GPIO {OPTO_BCM_PIN} read raised RuntimeError('no access to /dev/mem')")
    ]


def test_a_gpio_sensor_of_a_board_that_is_not_simulated_has_the_boards_pin(tmp_path: Path) -> None:
    layout = tmp_path / "layout.json"
    layout.write_text(
        (CONFIG / "gw.nolan.layout.json").read_text().replace('"SimGw108"', '"Gw108RevB"')
    )
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.plant_link = PlantLinkKind.InProcess
    devices = ScadaApp(app_settings=settings).plant.device_by_node

    pins = {name: d for name, d in devices.items() if isinstance(d, PinInput)}
    assert len(pins) == 5
    assert all(isinstance(pin, GpioPinInput) for pin in pins.values())
    assert len({pin.bcm_pin for pin in pins.values()}) == 5


def nolan_settings():
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    return settings


@pytest.mark.asyncio
async def test_a_sim_zones_pin_drives_its_heat_call(request: pytest.FixtureRequest) -> None:
    """The Nolan optos are DigitalZeroIsActive: pin 1 is idle, pin 0 is calling."""
    async with ScadaLiveTest(request=request, child_app_settings=nolan_settings()) as h:
        h.start_child1()
        data = h.child1_app.scada.data
        link = the_link(h.child1_app)

        link.show({OPTO_INPUT: 1}, READ_MS)
        await h.await_for(
            lambda: data.latest_channel_values.get(HEAT_CALL) == 0, "heat call idle, pin 1"
        )
        link.show({OPTO_INPUT: 0}, READ_MS)
        await h.await_for(
            lambda: data.latest_channel_values.get(HEAT_CALL) == 1, "heat call calling, pin 0"
        )
        link.show({OPTO_INPUT: 1}, READ_MS)
        await h.await_for(
            lambda: data.latest_channel_values.get(HEAT_CALL) == 0, "heat call idle again, pin 1"
        )


@pytest.mark.asyncio
async def test_a_sim_zone_already_calling_at_boot_is_seen_at_boot(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(request=request, child_app_settings=nolan_settings()) as h:
        h.add_child1()
        the_link(h.child1_app).show({OPTO_INPUT: 0}, READ_MS)
        h.start_child1()
        data = h.child1_app.scada.data
        await h.await_for(
            lambda: data.latest_channel_values.get(HEAT_CALL) == 1, "heat call calling at boot"
        )
