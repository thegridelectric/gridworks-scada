"""Reader↔bus pair tests: the thermistor reader driving a (faked) ADS1115
through the real I2cBus actor — config write, conversion wait, conversion
read, classification, publish.

The fixture's board is simulated, where the app puts the plant link behind
the reader. The rig puts the board's ADC there instead; the last tests are
the reader as a simulated house runs it.
"""

import asyncio
import json
import uuid
from pathlib import Path

import pytest

from actors.i2c_bus import I2cBus
from actors.i2c_thermistor_reader import I2cThermistorReader
from drivers import ads1115
from drivers.sim_i2c import SIM_THERMISTOR_VOLTS, SimI2c
from gwsproto.named_types import SyncedReadings
from gwproto.message import Message
from plant import ThermistorInput, ThermistorRead
from plant_link import InProcessPlantLink, LinkThermistorInput, PlantLinkKind
from scada_app import ScadaApp
from tests.utils.on_bus import reader_on_bus
from thermistor_inputs import Ads1115ThermistorInput

BUS_NAME = "i2c-bus"
READER_NAME = "gw108-thermistor-reader"
CONFIG = Path(__file__).parent.parent / "config"
READ_MS = 1_735_689_600_123


POR_DEFAULT_CONFIG = 0x8583  # the ADS1115 power-on config-register value


class FakeAds1115:
    """Emulates the ADS1115 single-shot dance over the big-endian block ops,
    including the config readback (a completed conversion reads back the
    written word, OS still set)."""

    def __init__(self, address: int) -> None:
        self.address = address
        self.volts_by_mux: dict[int, float] = {}
        self._config = POR_DEFAULT_CONFIG
        self.reset_after_config_write = False

    def write_i2c_block_data(self, addr: int, reg: int, data: list[int]) -> None:
        assert addr == self.address
        assert reg == ads1115.CONFIG_REG
        self._config = (data[0] << 8) | data[1]
        if self.reset_after_config_write:
            self._config = POR_DEFAULT_CONFIG

    def read_i2c_block_data(self, addr: int, reg: int, n: int) -> list[int]:
        assert addr == self.address
        assert n == 2
        if reg == ads1115.CONFIG_REG:
            return [(self._config >> 8) & 0xFF, self._config & 0xFF]
        assert reg == ads1115.CONVERSION_REG
        mux = ((self._config >> 12) & 0b111) - 0b100
        volts = self.volts_by_mux.get(mux, 0.0)
        raw = max(-32768, min(32767, int(volts * 32768 / ads1115.FULL_SCALE_VOLTS)))
        if raw < 0:
            raw += 0x10000
        return [(raw >> 8) & 0xFF, raw & 0xFF]


class Rig:
    """A reader + bus pair with hand-delivered messages and captured output."""

    def __init__(self, app: ScadaApp) -> None:
        self.bus = I2cBus(BUS_NAME, app)
        self.reader, self.adc = reader_on_bus(app, READER_NAME)
        self.fake_adc = FakeAds1115(self.adc.at.capability.I2cAddress)
        # What the bus built from the layout's board record, before the
        # rig swaps in its scripted ADC.
        self.board_i2c = self.bus.i2c
        self.bus.i2c = self.fake_adc
        self.published: list[tuple[str, object]] = []
        self.warnings: list[str] = []
        self.drop_bus_messages = False

        def reader_send(dst, payload, src=None):
            if dst.name == BUS_NAME:
                if not self.drop_bus_messages:
                    self.bus.process_message(
                        Message(Src=READER_NAME, Dst=BUS_NAME, Payload=payload)
                    )
            else:
                self.published.append((dst.name, payload))

        def bus_send(dst, payload, src=None):
            self.reader.process_message(
                Message(Src=BUS_NAME, Dst=dst.name, Payload=payload)
            )

        self.reader._send_to = reader_send
        self.bus._send_to = bus_send
        self.details: list[str] = []
        self.reader.send_warning = lambda summary, details="": (
            self.warnings.append(summary),
            self.details.append(details),
        )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    settings = ScadaApp.get_settings()
    # The pinned layout declares the i2c-bus node (gw.nolan.layout axiom 6
    # forces exactly one); boot straight off the fixture pair.
    settings.plant_link = PlantLinkKind.InProcess
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return Rig(app)


def test_reader_resolves_bus_node_from_layout(rig: Rig) -> None:
    assert rig.adc.at.bus_node.name == BUS_NAME


def test_adc_capability_resolves_via_own_board(rig: Rig) -> None:
    """The reader's ADC facts come from ITS board's device-type record — the
    typed chain component.board_component.device_type.ThermistorAdcs — never
    from a name scan across all records."""
    board = rig.reader.component.board_component
    assert board is not None
    assert board.gt.ComponentId == rig.reader.component.gt.BoardComponentId
    record = board.device_type
    assert record is not None
    assert rig.adc.at.capability in record.ThermistorAdcs
    assert rig.adc.at.capability.Name == rig.reader.component.gt.AdcName


def test_dangling_board_component_id_fails_decode(tmp_path: Path) -> None:
    """A dangling BoardComponentId is caught at the sema layer:
    gw.nolan.layout axiom 2 (BoardResolution) rejects the artifact at
    decode, before any dc load."""
    from sema_to_dc import load_layout

    settings = ScadaApp.get_settings()
    layout_dict = json.loads(Path(settings.paths.hardware_layout).read_text())
    reader_gt = next(
        c
        for c in layout_dict["Components"]
        if c["TypeName"] == "i2c.thermistor.reader.component.gt"
    )
    reader_gt["BoardComponentId"] = str(uuid.uuid4())
    poisoned = tmp_path / "layout-dangling-board.json"
    poisoned.write_text(json.dumps(layout_dict))
    with pytest.raises(Exception, match="Axiom 2 \\(BoardResolution\\)"):
        load_layout(
            poisoned,
            Path(__file__).parent.parent
            / "config"
            / "gw.nolan.operational.params.json",
        )


def test_reads_all_channels_through_bus(rig: Rig) -> None:
    for mux in range(4):
        rig.fake_adc.volts_by_mux[mux] = 1.5
    for device_cfg in rig.reader.device_configs.values():
        changed, microvolts, temp_c_x100 = asyncio.run(
            rig.reader.read_inputs(device_cfg)
        )
        assert changed
        assert abs(microvolts - 1_500_000) < 500  # one LSB at ±4.096 V is 125 µV
        assert temp_c_x100 is not None and temp_c_x100 > 0
    assert not rig.warnings


def test_the_boards_adc_reads_through_the_sim_bus(rig: Rig) -> None:
    """The board's ADC drive runs the real ADS1115 dance against the sim
    bus's SimAds1115 and classifies the constant it returns as a live
    thermistor."""
    rig.bus.i2c = rig.board_i2c
    assert isinstance(rig.bus.i2c, SimI2c)
    for device_cfg in rig.reader.device_configs.values():
        changed, microvolts, temp_c_x100 = asyncio.run(
            rig.reader.read_inputs(device_cfg)
        )
        assert changed
        assert abs(microvolts - SIM_THERMISTOR_VOLTS * 1_000_000) < 500
        assert temp_c_x100 is not None and temp_c_x100 > 0
    assert not rig.warnings


def test_floating_input_classifies_broken(rig: Rig) -> None:
    for mux in range(4):
        rig.fake_adc.volts_by_mux[mux] = 3.34  # at/above the 3.3 V reference
    device_cfg = next(iter(rig.reader.device_configs.values()))
    changed, microvolts, temp_c_x100 = asyncio.run(rig.reader.read_inputs(device_cfg))
    assert (changed, microvolts, temp_c_x100) == (False, None, None)
    assert rig.warnings == ["i2c-thermistor-broken"]
    assert rig.details == [
        f"{device_cfg.ChannelName}: 3.340000 V indicates a broken or missing thermistor"
    ]
    asyncio.run(rig.reader.read_inputs(device_cfg))
    assert len(rig.warnings) == 1, "once per failure streak"
    rig.fake_adc.volts_by_mux = {mux: 1.5 for mux in range(4)}
    changed, _, temp_c_x100 = asyncio.run(rig.reader.read_inputs(device_cfg))
    assert changed and temp_c_x100 is not None
    rig.fake_adc.volts_by_mux = {mux: 0.0 for mux in range(4)}
    asyncio.run(rig.reader.read_inputs(device_cfg))
    assert rig.warnings == ["i2c-thermistor-broken", "i2c-thermistor-shorted"]
    assert device_cfg.ChannelName not in rig.reader.latest_temp_c_x100


def test_chip_reset_mid_sequence_fails_readback_gate(rig: Rig) -> None:
    """A reset between config write and conversion read must NOT publish the
    previous conversion as this channel's value — the config readback gate
    catches the power-on default and fails the read."""
    for mux in range(4):
        rig.fake_adc.volts_by_mux[mux] = 1.5
    rig.fake_adc.reset_after_config_write = True
    device_cfg = next(iter(rig.reader.device_configs.values()))
    changed, microvolts, temp_c_x100 = asyncio.run(rig.reader.read_inputs(device_cfg))
    assert (changed, microvolts, temp_c_x100) == (False, None, None)
    assert rig.warnings == ["i2c-thermistor-read-failed"]
    assert rig.details == [
        f"{device_cfg.ChannelName}: ADS config readback mismatch: "
        f"wrote 0x{ads1115.config_word(rig.reader.electrical_cfg_by_device[device_cfg.ChannelName].AdcChannel, rig.reader.component.gt.DataRateSps):04x}, "
        f"read 0x{POR_DEFAULT_CONFIG:04x}"
    ]


def test_bus_timeout_is_contained(rig: Rig) -> None:
    rig.drop_bus_messages = True
    rig.adc.bus.timeout_s = 0.05
    device_cfg = next(iter(rig.reader.device_configs.values()))
    changed, microvolts, temp_c_x100 = asyncio.run(rig.reader.read_inputs(device_cfg))
    assert (changed, microvolts, temp_c_x100) == (False, None, None)
    assert rig.warnings == ["i2c-thermistor-read-failed"]


def test_publish_bundles_temps_and_microvolts(rig: Rig) -> None:
    for mux in range(4):
        rig.fake_adc.volts_by_mux[mux] = 1.5
    for device_cfg in rig.reader.device_configs.values():
        asyncio.run(rig.reader.read_inputs(device_cfg))
    rig.reader._publish()
    synced = [p for dst, p in rig.published if isinstance(p, SyncedReadings)]
    assert len(synced) == 1
    names = set(synced[0].ChannelNameList)
    for device_name in rig.reader.device_configs:
        assert device_name in names
    for electrical_name in rig.reader.electrical_configs:
        assert electrical_name in names


# --- the reader as a simulated house runs it ----------------------------------


def sim_reader() -> tuple[I2cThermistorReader, InProcessPlantLink, list[str]]:
    settings = ScadaApp.get_settings()
    settings.plant_link = PlantLinkKind.InProcess
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    link = app.plant_link
    assert isinstance(link, InProcessPlantLink)
    assert isinstance(app.plant.device(READER_NAME, ThermistorInput), LinkThermistorInput)
    reader = I2cThermistorReader(READER_NAME, app)
    warnings: list[str] = []
    reader.send_warning = lambda summary, details="": warnings.append(f"{summary}: {details}")
    reader.sent = []
    reader._send_to = lambda dst, payload, src=None: reader.sent.append((dst.name, payload))
    return reader, link, warnings


def test_a_simulated_reader_reports_the_plants_temperature_and_touches_no_bus() -> None:
    reader, link, warnings = sim_reader()
    device_cfg = next(iter(reader.device_configs.values()))
    temp_channel = device_cfg.ChannelName
    microvolts_channel = reader.electrical_cfg_by_device[temp_channel].ChannelName

    assert asyncio.run(reader.read_inputs(device_cfg)) == (False, None, None)
    reader._publish()
    assert reader.sent == [] and warnings == [], "nothing to read before the plant sends"

    link.show({temp_channel: 4_210}, READ_MS)
    assert asyncio.run(reader.read_inputs(device_cfg)) == (True, None, 4_210)
    reader._publish(device_cfg)
    synced = [p for _, p in reader.sent if isinstance(p, SyncedReadings)]
    assert [(p.ChannelNameList, p.ValueList) for p in synced] == [([temp_channel], [4_210])]

    link.show({temp_channel: 4_300, microvolts_channel: 1_480_000}, READ_MS)
    assert asyncio.run(reader.read_inputs(device_cfg)) == (True, 1_480_000, 4_300)
    reader._publish(device_cfg)
    synced = [p for _, p in reader.sent if isinstance(p, SyncedReadings)]
    assert (synced[-1].ChannelNameList, synced[-1].ValueList) == (
        [temp_channel, microvolts_channel],
        [4_300, 1_480_000],
    )
    assert BUS_NAME not in {dst for dst, _ in reader.sent}
    assert warnings == []


def test_a_simulated_reader_whose_plant_went_silent_fails_its_reads_once_a_streak() -> None:
    reader, link, warnings = sim_reader()
    device_cfg = next(iter(reader.device_configs.values()))
    temp_channel = device_cfg.ChannelName
    now = [0.0]
    link.monotonic = lambda: now[0]
    link.show({temp_channel: 4_210}, READ_MS)
    asyncio.run(reader.read_inputs(device_cfg))

    now[0] = link.silent_after_s + 1
    for _ in range(3):
        assert asyncio.run(reader.read_inputs(device_cfg)) == (False, None, None)
    assert warnings == [f"i2c-thermistor-read-failed: {temp_channel}: the plant is silent"]
    assert temp_channel not in reader.latest_temp_c_x100

    link.show({temp_channel: 4_210}, READ_MS)
    _, _, temp_c_x100 = asyncio.run(reader.read_inputs(device_cfg))
    assert temp_c_x100 == 4_210


def test_a_board_that_is_not_simulated_has_its_adc_behind_the_reader(tmp_path: Path) -> None:
    layout = tmp_path / "layout.json"
    layout.write_text(
        (CONFIG / "gw.nolan.layout.json").read_text().replace('"SimGw108"', '"Gw108RevB"')
    )
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    adc = ScadaApp(app_settings=settings).plant.device(READER_NAME, ThermistorInput)

    assert isinstance(adc, Ads1115ThermistorInput)
    assert adc.at.bus_node.name == BUS_NAME
    assert set(adc.at.channels.device_configs) == set(adc.at.channels.electrical_cfg_by_device)


def test_a_conversion_that_cannot_be_made_is_said_and_not_raised(rig: Rig) -> None:
    """A beta of zero divides by zero in the conversion."""
    rig.fake_adc.volts_by_mux = {mux: 1.5 for mux in range(4)}
    temp_channel, device_cfg = next(iter(rig.adc.at.channels.device_configs.items()))
    rig.adc.at.channels.device_configs[temp_channel] = device_cfg.model_copy(
        update={"ThermistorBeta": 0}
    )

    read = asyncio.run(rig.adc.read(temp_channel))
    assert read == ThermistorRead(None, None, read.said)
    assert [(s.summary, s.streak) for s in read.said] == [("i2c-thermistor-invalid-reading", True)]

    rig.adc.at.channels.device_configs[temp_channel] = device_cfg
    assert asyncio.run(rig.adc.read(temp_channel)).said == ()
