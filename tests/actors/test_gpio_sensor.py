"""A GPIO sensor publishes its first reading whatever the pin reads, so a
zone already calling when the scada boots is seen at boot."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from actors.gpio_sensor import GpioSensor
from gwsproto.named_types import SingleReading
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
OPTO = "zone1-bedrooms-opto"
HEAT_CALL = "zone1-bedrooms-heat-call"


def boot() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("pin_reads", [0, 1])
async def test_first_reading_publishes_whatever_the_pin_reads(pin_reads: int) -> None:
    sensor = boot().get_communicator_as_type(OPTO, GpioSensor)
    assert sensor is not None
    sensor.GPIO = SimpleNamespace(input=lambda pin: pin_reads)
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
        sensor = h.child1_app.get_communicator_as_type(OPTO, GpioSensor)
        assert sensor is not None

        await h.await_for(
            lambda: data.latest_channel_values.get(HEAT_CALL) == 0, "heat call idle, pin 1"
        )
        sensor.sim_pin_value = 0
        await h.await_for(
            lambda: data.latest_channel_values.get(HEAT_CALL) == 1, "heat call calling, pin 0"
        )
        sensor.sim_pin_value = 1
        await h.await_for(
            lambda: data.latest_channel_values.get(HEAT_CALL) == 0, "heat call idle again, pin 1"
        )


@pytest.mark.asyncio
async def test_a_sim_zone_already_calling_at_boot_is_seen_at_boot(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(request=request, child_app_settings=nolan_settings()) as h:
        h.add_child1()
        sensor = h.child1_app.get_communicator_as_type(OPTO, GpioSensor)
        assert sensor is not None
        sensor.sim_pin_value = 0
        h.start_child1()
        data = h.child1_app.scada.data
        await h.await_for(
            lambda: data.latest_channel_values.get(HEAT_CALL) == 1, "heat call calling at boot"
        )
