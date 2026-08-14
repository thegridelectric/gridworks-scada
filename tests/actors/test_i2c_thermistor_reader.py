"""Reader↔bus pair tests: the thermistor reader driving a (faked) ADS1115
through the real I2cBus actor — config write, conversion wait, conversion
read, classification, publish.
"""

import asyncio
import json
import shutil
import uuid
from pathlib import Path

import pytest

from actors.i2c_bus import I2cBus
from actors.i2c_thermistor_reader import I2cThermistorReader
from drivers import ads1115
from gwsproto.named_types import SyncedReadings
from gwproto.message import Message
from actors.config import DEFAULT_OPS_PARAMS_FILE
from scada_app import ScadaApp

BUS_NAME = "i2c-bus"
READER_NAME = "gw108-thermistor-reader"


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
        self.reader = I2cThermistorReader(READER_NAME, app)
        self.fake_adc = FakeAds1115(self.reader.adc_capability.I2cAddress)
        self.bus.is_simulated = False
        self.bus.i2c = self.fake_adc
        self.reader.is_simulated = False
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
        self.reader.send_warning = (
            lambda summary, details="": self.warnings.append(summary)
        )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    settings = ScadaApp.get_settings()
    settings.is_simulated = True
    layout_dict = json.loads(Path(settings.paths.hardware_layout).read_text())
    layout_dict["ShNodes"].append(
        {
            "Name": BUS_NAME,
            "ActorClass": "I2cBus",
            "ActorHierarchyName": f"s.{BUS_NAME}",
            "ShNodeId": str(uuid.uuid4()),
            "TypeName": "spaceheat.node.gt",
            "Version": "303",
        }
    )
    layout_path = tmp_path / "layout-with-bus.json"
    layout_path.write_text(json.dumps(layout_dict))
    # the pair travels together: ops params sit beside the layout under the
    # fixed name the scada resolves to
    shutil.copyfile(
        Path(settings.paths.operational_params), tmp_path / DEFAULT_OPS_PARAMS_FILE
    )
    settings.paths.hardware_layout = layout_path
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return Rig(app)


def test_reader_resolves_bus_node_from_layout(rig: Rig) -> None:
    assert rig.reader.bus_node is not None
    assert rig.reader.bus_node.name == BUS_NAME


def test_adc_capability_resolves_via_own_board(rig: Rig) -> None:
    """The reader's ADC facts come from ITS board's device-type record — the
    typed chain component.board_component.device_type.ThermistorAdcs — never
    from a name scan across all records."""
    board = rig.reader.component.board_component
    assert board is not None
    assert board.gt.ComponentId == rig.reader.component.gt.BoardComponentId
    record = board.device_type
    assert record is not None
    assert rig.reader.adc_capability in record.ThermistorAdcs
    assert rig.reader.adc_capability.Name == rig.reader.component.gt.AdcName


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


def test_floating_input_classifies_broken(rig: Rig) -> None:
    for mux in range(4):
        rig.fake_adc.volts_by_mux[mux] = 3.34  # at/above the 3.3 V reference
    device_cfg = next(iter(rig.reader.device_configs.values()))
    changed, microvolts, temp_c_x100 = asyncio.run(rig.reader.read_inputs(device_cfg))
    assert (changed, microvolts, temp_c_x100) == (False, None, None)
    assert rig.warnings == ["i2c-thermistor-broken"]


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


def test_bus_timeout_is_contained(rig: Rig) -> None:
    rig.drop_bus_messages = True
    rig.reader.bus_op_timeout_s = 0.05
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
