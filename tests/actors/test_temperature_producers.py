"""Temperature producers emit by their channel's declared encoding: the same
measurement, posted to a channel declared in either Celsius encoding, reads
back as the same temperature."""

import importlib
import json
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from actors.api_btu_meter import ApiBtuMeter
from actors.api_tank_module import OPEN_THERMISTOR_REPORT_S, PICO_VOLTS, ApiTankModule
from actors.derived_generator import DerivedGenerator
from actors.hubitat_poller import HubitatPoller
from drivers.driver_result import DriverOutcome
from gwsproto.enums import LogLevel, TelemetryName
from gwsproto.named_types import Glitch, MicroVolts, MultichannelSnapshot, SingleReading, SyncedReadings
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.type_helpers import MakerAPIAttributeGt
from result import Ok
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
WILLOW = ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")
NOLAN = ("gw.nolan.layout.json", "gw.nolan.operational.params.json")
CELSIUS_ENCODINGS = [TelemetryName.WaterTempCTimes1000, TelemetryName.CelsiusTimes100]


def declared(pair: tuple[str, str], channel_names: list[str], encoding: TelemetryName) -> dict:
    """The pair's sim layout with `channel_names` declared in `encoding`."""
    layout = json.loads((CONFIG / pair[0]).read_text())
    for ch in layout["DataChannels"]:
        if ch["Name"] in channel_names:
            ch["TelemetryName"] = encoding.value
    return layout


def boot(tmp_path: Path, pair: tuple[str, str], layout: dict) -> ScadaApp:
    layout_path = tmp_path / pair[0]
    layout_path.write_text(json.dumps(layout))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout_path
    settings.paths.operational_params = CONFIG / pair[1]
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.mark.parametrize("encoding", CELSIUS_ENCODINGS)
def test_tank_module_emits_by_the_device_channel_encoding(tmp_path: Path, encoding: TelemetryName) -> None:
    channel_names = [f"buffer-depth{i}-device" for i in (1, 2, 3)]
    app = boot(tmp_path, WILLOW, declared(WILLOW, channel_names, encoding))
    tank = app.get_communicator_as_type("buffer", ApiTankModule)
    assert tank is not None
    sent: list[SyncedReadings] = []
    tank._send_to = lambda dst, payload, src=None: sent.append(payload)
    volts = 1.2
    assert tank.pico_uid

    tank._process_microvolts(
        MicroVolts(
            HwUid=tank.pico_uid,
            AboutNodeNameList=[tank.depth_about_nodes[i] for i in (1, 2, 3)],
            MicroVoltsList=[int(volts * 1e6)] * 3,
        )
    )

    readings = sent[0]
    expected_f = tank.simple_beta(volts, fahrenheit=True)
    for name in channel_names:
        raw = readings.ValueList[readings.ChannelNameList.index(name)]
        assert tank.layout.channel_registry.temperature(name, raw).f == pytest.approx(expected_f, abs=0.02)


def test_open_thermistor_is_one_warning_glitch_a_day_and_no_temperature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = boot(tmp_path, WILLOW, json.loads((CONFIG / WILLOW[0]).read_text()))
    tank = app.get_communicator_as_type("buffer", ApiTankModule)
    assert tank is not None
    assert tank.pico_uid
    sent: list = []
    tank._send_to = lambda dst, payload, src=None: sent.append(payload)
    about = [tank.depth_about_nodes[i] for i in (1, 2, 3)]

    def post(depth3_volts: float) -> None:
        tank._process_microvolts(
            MicroVolts(
                HwUid=tank.pico_uid,
                AboutNodeNameList=about,
                MicroVoltsList=[1_200_000, 1_200_000, int(depth3_volts * 1e6)],
            )
        )

    post(PICO_VOLTS)
    post(PICO_VOLTS)
    glitches = [p for p in sent if isinstance(p, Glitch)]
    assert [(g.Type, g.Summary) for g in glitches] == [(LogLevel.Warning, "open-thermistor")]
    assert about[2] in glitches[0].Details
    for readings in (p for p in sent if isinstance(p, SyncedReadings)):
        assert f"{about[2]}-device" not in readings.ChannelNameList
        assert f"{about[0]}-device" in readings.ChannelNameList

    # a reconnected thermistor reads again; opening again the same day is silent
    post(1.2)
    assert f"{about[2]}-device" in sent[-1].ChannelNameList
    post(PICO_VOLTS)
    assert len([p for p in sent if isinstance(p, Glitch)]) == 1

    # still open a day later: reported again
    a_day_on = time.time() + OPEN_THERMISTOR_REPORT_S
    monkeypatch.setattr(time, "time", lambda: a_day_on)
    post(PICO_VOLTS)
    assert len([p for p in sent if isinstance(p, Glitch)]) == 2


@pytest.mark.parametrize("encoding", CELSIUS_ENCODINGS)
def test_btu_meter_emits_by_the_temperature_channel_encoding(tmp_path: Path, encoding: TelemetryName) -> None:
    channel_names = ["hp-lwt", "hp-ewt"]
    app = boot(tmp_path, NOLAN, declared(NOLAN, channel_names, encoding))
    btu = app.get_communicator_as_type("primary-btu", ApiBtuMeter)
    assert btu is not None
    sent: list[SyncedReadings] = []
    btu._send_to = lambda dst, payload, src=None: sent.append(payload)

    btu._process_multichannel_snapshot(
        MultichannelSnapshot(
            HwUid=btu.pico_uid,
            ChannelNameList=["primary-flow", "hp-lwt", "hp-ewt"],
            MeasurementList=[350, 4512, 3987],
            UnitList=["GpmTimes100", "CelsiusTimes100", "CelsiusTimes100"],
        )
    )

    readings = sent[0]
    registry = btu.layout.channel_registry
    assert readings.ValueList[0] == 350
    assert registry.temperature("hp-lwt", readings.ValueList[1]).f == pytest.approx(45.12 * 9 / 5 + 32)
    assert registry.temperature("hp-ewt", readings.ValueList[2]).f == pytest.approx(39.87 * 9 / 5 + 32)


@pytest.mark.parametrize("encoding", CELSIUS_ENCODINGS)
def test_derived_generator_takes_an_affine_input_in_either_celsius_encoding(
    tmp_path: Path, encoding: TelemetryName
) -> None:
    """The Nolan pair's `buffer-depth1` is affine (M 1, B 0) over
    `buffer-depth1-device`."""
    app = boot(tmp_path, NOLAN, declared(NOLAN, ["buffer-depth1-device"], encoding))
    generator = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert generator is not None
    sent: list[SingleReading] = []
    generator._send_to = lambda dst, payload, src=None: sent.append(payload)
    registry = generator.layout.channel_registry

    generator.handle_affine(
        generator.layout.derived_channels["buffer-depth1"],
        SingleReading(
            ChannelName="buffer-depth1-device",
            Value=registry.temperature_from_c("buffer-depth1-device", 50.0).raw,
            ScadaReadTimeUnixMs=1_700_000_000_000,
        ),
    )

    assert registry.temperature("buffer-depth1", sent[0].Value).f == pytest.approx(122.0, abs=0.01)


@pytest.mark.parametrize("encoding", CELSIUS_ENCODINGS)
def test_tsnap_driver_emits_by_the_channel_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, encoding: TelemetryName
) -> None:
    """The driver imports the ADS1115 hardware libraries, absent off a pi, so
    they are stubbed and the voltage read is supplied."""
    for name in ("adafruit_ads1x15", "adafruit_ads1x15.ads1115", "adafruit_ads1x15.analog_in", "board", "busio"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    sys.modules["adafruit_ads1x15.analog_in"].AnalogIn = object  # type: ignore[attr-defined]
    sys.modules["busio"].I2C = object  # type: ignore[attr-defined]
    module = importlib.import_module("drivers.multipurpose_sensor.gridworks_tsnap1__multipurpose_sensor_driver")
    monkeypatch.delitem(sys.modules, module.__name__)
    driver_class = module.GridworksTsnap1_MultipurposeSensorDriver
    app = boot(tmp_path, WILLOW, declared(WILLOW, ["buffer-depth1-device"], encoding))
    channel = app.hardware_layout.data_channels["buffer-depth1-device"]
    driver = driver_class.__new__(driver_class)
    volts = 1.2
    driver.read_voltage = lambda ch: Ok(DriverOutcome[float](volts))

    outcome = driver.read_telemetry_values([channel]).unwrap()

    expected_c = driver_class.voltage_to_c(volts).unwrap()
    raw = outcome.value[channel.Name]
    assert raw is not None
    assert app.hardware_layout.channel_registry.temperature(channel.Name, raw).f == pytest.approx(
        expected_c * 9 / 5 + 32, abs=0.02
    )


@pytest.mark.parametrize("encoding", [TelemetryName.AirTempFTimes1000, TelemetryName.CelsiusTimes100])
def test_hubitat_poller_emits_a_fahrenheit_reading_by_the_channel_encoding(
    tmp_path: Path, encoding: TelemetryName
) -> None:
    """No sim pair boots a Hubitat, so the poller's converter is made for an
    attribute over the willow pair's zone temperature channel."""
    channel_name = "zone1-main-temp"
    app = boot(tmp_path, WILLOW, declared(WILLOW, [channel_name], encoding))
    attribute = MakerAPIAttributeGt(
        AttributeName="temperature",
        ChannelName=channel_name,
        NodeName="zone1-main",
        TelemetryName=encoding,
        Unit="Fahrenheit",
    )

    converter = HubitatPoller._make_value_converter(SimpleNamespace(_services=app), attribute)

    assert converter is not None
    raw = converter("69.0")
    assert raw is not None
    assert app.hardware_layout.channel_registry.temperature(channel_name, raw).f == pytest.approx(69.0, abs=0.01)
    assert converter("not a number") is None


def test_hubitat_poller_refuses_a_temperature_attribute_over_a_non_temperature_channel(tmp_path: Path) -> None:
    app = boot(tmp_path, WILLOW, declared(WILLOW, [], TelemetryName.CelsiusTimes100))
    attribute = MakerAPIAttributeGt(
        AttributeName="temperature",
        ChannelName="hp-odu-pwr",
        NodeName="zone1-main",
        TelemetryName=TelemetryName.PowerW,
        Unit="Fahrenheit",
    )

    with pytest.raises(ValueError):
        HubitatPoller._make_value_converter(SimpleNamespace(_services=app), attribute)
