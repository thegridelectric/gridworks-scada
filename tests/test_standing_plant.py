"""The standing plant: the plant link that carries its own plant, so a
simulated layout runs with nothing beside the scada."""

from pathlib import Path

import pytest
from gwsproto.enums import ActorClass, ChangeRelayPin, RelayClosedOrOpen, TelemetryName

from drivers import ads1115
from drivers.sim_i2c import SIM_THERMISTOR_RAW
from plant_link import PlantLinkKind
from scada_app import ScadaApp
from standing_plant import StandingPico, StandingPlantLink
from tests.utils.scada_live_test_helper import ScadaLiveTest
from thermistor_inputs import resolve_thermistor_adc, thermistor_reading

CONFIG = Path(__file__).parent / "config"
HAZEL = "gw.house0.no.sieg.hazel"
ORANGE = "gw.house0.orange"
NOLAN = "gw.nolan"
PERIOD = 60
VALUES = {"buffer-depth1-micro-v": 1_000_000, "buffer-depth2-micro-v": 1_100_000}


def pico(life_s: int | None = None, reboot_s: int | None = None) -> StandingPico:
    return StandingPico(
        VALUES, capture_period_s=PERIOD, life_s=life_s, reboot_s=reboot_s, booted_at=0.0
    )


def posts(src: StandingPico, instants: list[float]) -> list[float]:
    """The instants at which ticking at each instant posted."""
    return [t for t in instants if src.tick(t)]


def test_a_pico_posts_at_the_capture_period() -> None:
    src = pico()
    assert src.tick(0.0) == VALUES
    assert posts(src, [1.0, 30.0, 59.0, 60.0, 61.0, 119.0, 120.0]) == [60.0, 120.0]


def test_no_life_means_it_never_dies() -> None:
    every_period = [float(t) for t in range(0, 24 * 3600, PERIOD)]
    assert posts(pico(), every_period) == every_period


def test_a_pico_goes_silent_after_its_life() -> None:
    src = pico(life_s=150)
    assert posts(src, [0.0, 60.0, 120.0, 150.0, 180.0, 3600.0]) == [0.0, 60.0, 120.0]
    assert not src.alive


def test_a_dead_pico_stays_dead_without_a_reboot_time() -> None:
    src = pico(life_s=10)
    assert posts(src, [0.0, 10.0]) == [0.0]
    src.relay_state(RelayClosedOrOpen.RelayOpen, 20.0)
    src.relay_state(RelayClosedOrOpen.RelayClosed, 25.0)
    assert posts(src, [30.0, 300.0, 3000.0]) == []


def test_a_pico_reboots_after_the_relay_closes_following_an_open() -> None:
    src = pico(life_s=10, reboot_s=15)
    assert posts(src, [0.0, 10.0]) == [0.0]
    src.relay_state(RelayClosedOrOpen.RelayOpen, 20.0)
    src.relay_state(RelayClosedOrOpen.RelayClosed, 25.0)
    # It boots at 40 and its life runs from that boot.
    assert posts(src, [30.0, 39.0, 40.0, 45.0, 49.0, 50.0]) == [40.0]
    assert not src.alive


def test_the_relay_opening_kills_a_living_pico() -> None:
    src = pico(reboot_s=5)
    assert posts(src, [0.0]) == [0.0]
    src.relay_state(RelayClosedOrOpen.RelayOpen, 1.0)
    assert posts(src, [60.0, 120.0]) == []
    src.relay_state(RelayClosedOrOpen.RelayClosed, 130.0)
    assert posts(src, [134.0, 135.0, 194.0, 195.0]) == [135.0, 195.0]


def test_a_close_with_no_open_before_it_schedules_nothing() -> None:
    src = pico(life_s=10, reboot_s=5)
    assert posts(src, [0.0, 10.0]) == [0.0]
    src.relay_state(RelayClosedOrOpen.RelayClosed, 20.0)
    assert posts(src, [25.0, 100.0]) == []


class Now:
    def __init__(self) -> None:
        self.s = 1_794_300_000.0

    def __call__(self) -> float:
        return self.s


def standing_settings(pair: str):
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / f"{pair}.layout.json"
    settings.paths.operational_params = CONFIG / f"{pair}.operational.params.json"
    settings.plant_link = PlantLinkKind.Standing
    settings.paths.mkdirs()
    return settings


def standing(pair: str) -> tuple[ScadaApp, StandingPlantLink, Now]:
    app = ScadaApp(app_settings=standing_settings(pair))
    app.instantiate()
    link = app.plant_link
    assert isinstance(link, StandingPlantLink)
    now = Now()
    link.wall = now
    for src in link.picos:
        src.booted_at = now.s
    return app, link, now


@pytest.mark.parametrize("pair", [HAZEL, ORANGE, NOLAN])
def test_the_first_flux_shows_every_channel_a_simulated_device_senses(pair: str) -> None:
    app, link, now = standing(pair)
    layout = app.hardware_layout
    sensed = set(link.sensor_by_channel) | link.polled_channels
    assert sensed
    wanted = {
        name
        for name in sensed
        if not layout.channel_disabled(name)
        and not layout.node_disabled(layout.data_channels[name].CapturedByNodeName)
    }

    shown = set(link.showing(now.s))

    assert wanted - shown == set()
    assert shown - sensed == set()


def test_a_sim_sensor_channel_shows_every_five_seconds_at_its_telemetrys_value() -> None:
    app, link, now = standing(HAZEL)
    layout = app.hardware_layout
    start = now.s
    assert layout.data_channels["hp-lwt"].TelemetryName == TelemetryName.CelsiusTimes100

    shown_at = [t for t in range(12) if "hp-lwt" in link.showing(start + t)]

    assert shown_at == [0, 5, 10]
    assert link.sim_sensors["hp-lwt"] == 5_000
    assert link.sim_sensors["store-flow"] == 400


def test_a_metered_channel_is_in_every_flux_at_no_power() -> None:
    _, link, now = standing(HAZEL)
    metered = set(link.polled_channels)
    assert metered

    for t in range(8):
        showing = link.showing(now.s + t)
        assert {showing[name] for name in metered} == {0}


def test_a_board_thermistor_reads_what_the_simulated_adc_holds() -> None:
    """The microvolts are the voltage a simulated ADC's register holds, and
    the temperature is the reader's own conversion of it."""
    app, link, now = standing(NOLAN)
    reader = next(
        node
        for node in app.hardware_layout.nodes.values()
        if node.actor_class == ActorClass.I2cThermistorReader
    )
    adc = resolve_thermistor_adc(app.hardware_layout, reader)
    volts = ads1115.volts_from_raw(SIM_THERMISTOR_RAW)
    showing = link.showing(now.s)
    assert adc.channels.electrical_cfg_by_device

    for temp_channel, electrical_cfg in adc.channels.electrical_cfg_by_device.items():
        read = thermistor_reading(adc, temp_channel, volts)
        assert read.said == ()
        assert showing[temp_channel] == read.temp_c_x100
        assert showing[electrical_cfg.ChannelName] == read.microvolts == 200_000


def test_cycling_the_vdc_relay_revives_the_picos_that_died() -> None:
    _, link, now = standing(HAZEL)
    start = now.s
    tank = next(src for src in link.picos if "buffer-depth1-micro-v" in src.values)
    assert (tank.life_s, tank.reboot_s) == (120, 20)

    def tank_posts(seconds: range) -> list[int]:
        return [t for t in seconds if "buffer-depth1-micro-v" in link.showing(start + t)]

    assert tank_posts(range(0, 200)) == [0, 60]

    now.s = start + 200
    link.set_relay("vdc-relay", ChangeRelayPin.Energize)
    now.s = start + 205
    link.set_relay("vdc-relay", ChangeRelayPin.DeEnergize)

    assert tank_posts(range(205, 300)) == [225, 285]


def test_another_relay_leaves_the_picos_alone() -> None:
    _, link, now = standing(HAZEL)
    link.set_relay("store-pump-relay", ChangeRelayPin.Energize)
    link.set_relay("store-pump-relay", ChangeRelayPin.DeEnergize)
    assert all(src.alive for src in link.picos)
    assert link.relay("store-pump-relay") == ChangeRelayPin.DeEnergize


@pytest.mark.asyncio
async def test_a_scada_on_the_standing_plant_sees_its_whole_plant(
    request: pytest.FixtureRequest,
) -> None:
    """A scada with nothing beside it: within the first ticks every sensed
    channel has a value, the meter has read, and no flux has carried a
    channel that nothing reads."""
    async with ScadaLiveTest(request=request, child_app_settings=standing_settings(ORANGE)) as h:
        h.start_child1()
        app = h.child1_app
        link = app.plant_link
        assert isinstance(link, StandingPlantLink)
        data = app.scada.data
        layout = app.hardware_layout
        wanted = {
            name
            for name in set(link.sensor_by_channel) | link.polled_channels
            if not layout.channel_disabled(name)
            and not layout.node_disabled(layout.data_channels[name].CapturedByNodeName)
        }

        await h.await_for(
            lambda: data.latest_power_w == 0
            and all(data.latest_channel_values.get(name) is not None for name in wanted),
            "the scada holds a value for every channel the plant shows",
        )

        assert data.latest_channel_values["hp-lwt"] == 5_000
        assert link.unsensed_channels == set()
