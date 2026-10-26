"""The layout's DisabledNodeNames and DisabledChannelNames are the one home
for "the house cannot serve this yet". A disabled node's actor is built but
idle: it keeps its routes, the pico-cycler neither lists it nor cycles for
it, and it never reports a reading, a missing pico or a flatlined channel.
A disabled channel is skipped by its capturing actor and by the derived
generator, is left out of reports and the UnknownChannels line, and the
scada names the whole roster in one Warning glitch. The Nolan sim layout
already disables several channels; the tests disable floor1 as a node."""

import asyncio
import json
from pathlib import Path

import pytest

from actors.api_btu_meter import ApiBtuMeter
from actors.api_tank_module import ApiTankModule
from actors.derived_generator import DerivedGenerator
from actors.i2c_thermistor_reader import I2cThermistorReader
from actors.pico_cycler import PicoCycler
from actors.power_meter import PowerMeter, PowerMeterDriverThread
from gwsproto.named_types import ChannelFlatlined, Glitch, MicroVolts, PicoMissing
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
LAYOUT = "gw.nolan.layout.json"
OPS = "gw.nolan.operational.params.json"
DISABLED = "floor1"
DISABLED_CHANNELS = [f"{DISABLED}-depth{i}-{kind}" for i in (1, 2, 3) for kind in ("device", "micro-v")]
DISABLED_DERIVED = ["zone1-bedrooms-floor-temp", "zone2-living-rm-floor-temp", "zone4-garage-floor-temp"]
"""The identity floor temps over floor1's depths: disabled with it, as the
EnabledDerivedChannelsHaveLiveInputs axiom requires."""


def boot(tmp_path: Path, disabled_channels: list[str] | None = None) -> ScadaApp:
    layout = json.loads((CONFIG / LAYOUT).read_text())
    if disabled_channels is None:
        layout["DisabledNodeNames"] = [DISABLED]
        layout["DisabledChannelNames"] += DISABLED_CHANNELS + DISABLED_DERIVED
    else:
        layout["DisabledChannelNames"] += disabled_channels
    layout_path = tmp_path / LAYOUT
    layout_path.write_text(json.dumps(layout))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout_path
    settings.paths.operational_params = CONFIG / OPS
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def capture(actor) -> list:
    sent: list = []
    actor._send_to = lambda dst, payload, src=None: sent.append(payload)
    actor._send = lambda message: None
    return sent


def flatlined(sent: list) -> set[str]:
    return {p.Channel.Name for p in sent if isinstance(p, ChannelFlatlined)}


def test_the_layout_carries_the_lists_and_reports_none_of_them(tmp_path: Path) -> None:
    layout = boot(tmp_path).scada.layout
    assert layout.node_disabled(DISABLED)
    assert not layout.node_disabled("fancoil")
    assert layout.channel_disabled("fancoil-depth3-device")
    assert layout.unreported_channels == layout.disabled_channel_names
    assert set(DISABLED_CHANNELS + DISABLED_DERIVED) <= layout.disabled_channel_names
    # a disabled DerivedChannel takes no input
    assert not layout.feeds_derived([f"{DISABLED}-depth1-device"])


def test_the_cycler_does_not_list_a_disabled_pico(tmp_path: Path) -> None:
    app = boot(tmp_path)
    cycler = app.scada.get_communicator(HSNN.pico_cycler)
    assert isinstance(cycler, PicoCycler)
    assert DISABLED not in {actor.name for actor in cycler.pico_actors}
    assert "fancoil" in {actor.name for actor in cycler.pico_actors}
    assert len(cycler.picos) == len(cycler.pico_actors) == len(cycler.pico_by_actor)


def test_the_layout_keeps_a_disabled_picos_channels(tmp_path: Path) -> None:
    layout = boot(tmp_path).scada.layout
    for depth in (1, 2, 3):
        assert f"{DISABLED}-depth{depth}-device" in layout.data_channels
    assert "zone1-bedrooms-floor-temp" in layout.derived_channels


@pytest.mark.asyncio
async def test_a_disabled_pico_actor_never_reports_missing(tmp_path: Path) -> None:
    app = boot(tmp_path)
    tank = app.get_communicator_as_type(DISABLED, ApiTankModule)
    assert tank is not None
    assert tank.disabled
    sent = capture(tank)
    tank.liveness.report_due = lambda now: True

    task = asyncio.create_task(tank.main())
    await asyncio.sleep(0.05)
    tank._stop_requested = True
    task.cancel()

    assert sent == []


def test_a_disabled_pico_actor_reads_nothing_its_pico_posts(tmp_path: Path) -> None:
    app = boot(tmp_path)
    tank = app.get_communicator_as_type(DISABLED, ApiTankModule)
    assert tank is not None
    sent = capture(tank)
    assert tank.pico_uid
    tank._process_microvolts(
        MicroVolts(
            HwUid=tank.pico_uid,
            AboutNodeNameList=[f"{DISABLED}-depth1", f"{DISABLED}-depth2", f"{DISABLED}-depth3"],
            MicroVoltsList=[1_500_000, 1_500_000, 1_500_000],
        )
    )
    assert sent == []


@pytest.mark.asyncio
async def test_an_enabled_pico_actor_reports_missing_but_not_its_disabled_channel(tmp_path: Path) -> None:
    app = boot(tmp_path)
    tank = app.get_communicator_as_type("fancoil", ApiTankModule)
    assert tank is not None
    assert not tank.disabled
    sent = capture(tank)
    tank.liveness.report_due = lambda now: True

    task = asyncio.create_task(tank.main())
    await asyncio.sleep(0.05)
    tank._stop_requested = True
    task.cancel()

    assert any(isinstance(p, PicoMissing) for p in sent)
    assert "fancoil-depth1-device" in flatlined(sent)
    assert "fancoil-depth3-device" not in flatlined(sent)


def test_a_btu_meter_neither_flatlines_nor_warns_on_its_disabled_pipes(tmp_path: Path) -> None:
    app = boot(tmp_path)
    btu = app.get_communicator_as_type("store-btu", ApiBtuMeter)
    assert btu is not None
    assert {ch.Name for ch in btu.flatlined_channels()} == {"store-flow"}
    sent = capture(btu)
    btu.liveness.report_due = lambda now: True
    for liveness in btu.channel_liveness.values():
        liveness.report_due = lambda now: True
    btu.check_liveness()
    assert flatlined(sent) == {"store-flow"}
    assert not [p for p in sent if isinstance(p, Glitch) and "pipe" in p.Details]


def test_the_power_meter_leaves_a_disabled_channel_out(tmp_path: Path) -> None:
    app = boot(tmp_path)
    meter = app.get_communicator_as_type(CoreNodeNames.asset_power_meter, PowerMeter)
    assert meter is not None
    assert isinstance(meter._sync_thread, PowerMeterDriverThread)
    names = {ch.Name for ch in meter._sync_thread.my_channels}
    assert "primary-pump-pwr" not in names
    assert "hp-odu-pwr" in names


def test_the_derived_generator_skips_a_disabled_derived_channel(tmp_path: Path) -> None:
    app = boot(tmp_path)
    generator = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert generator is not None
    fed = {dc.Name for dcs in generator.derived_by_input.values() for dc in dcs}
    assert not fed & set(DISABLED_DERIVED)
    assert f"{DISABLED}-depth1-device" not in generator.derived_by_input


def test_unknown_channels_leaves_disabled_channels_out(tmp_path: Path) -> None:
    app = boot(tmp_path)
    unknown = app.scada.data.unknown_channels()
    assert not set(unknown.no_value) & app.scada.layout.disabled_channel_names
    assert "fancoil-depth1-device" in unknown.no_value


def test_the_scada_names_the_disabled_roster_once(tmp_path: Path) -> None:
    app = boot(tmp_path)
    glitch = app.scada.disabled_roster_glitch()
    assert glitch is not None
    assert glitch.Summary == "disabled-roster"
    assert DISABLED in glitch.Details
    assert "fancoil-depth3-device" in glitch.Details


def test_the_thermistor_reader_drops_a_pair_when_either_half_is_disabled(tmp_path: Path) -> None:
    app = boot(tmp_path, disabled_channels=["zone1-bedrooms-gw-temp", "zone1-bedrooms-set"])
    reader = app.get_communicator_as_type("gw108-thermistor-reader", I2cThermistorReader)
    assert reader is not None
    assert "zone1-bedrooms-gw-temp" not in reader.device_configs
    assert "zone1-bedrooms-gw-microvolts" not in reader.electrical_configs
    assert "zone2-living-rm-gw-temp" in reader.device_configs
