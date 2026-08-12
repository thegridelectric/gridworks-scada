"""Actor-level tests for the I2cBus serialized executor.

The pinned test layout does not declare an i2c-bus node yet (the layout gains
it with the reader→bus move); the fixture here appends one in-memory before
boot, which also exercises the actors/__init__ registration path.
"""

import json
import uuid
from pathlib import Path

import pytest

from actors.i2c_bus import I2cBus
from drivers import mcp4728
from drivers.sim_i2c import SimI2c
from gwsproto.enums import I2cOperation
from gwsproto.named_types import (
    I2cBitAddress,
    I2cReadBit,
    I2cReadBytes,
    I2cReadReg,
    I2cRegAddress,
    I2cResult,
    I2cWriteBit,
    I2cWriteByte,
    I2cWriteReg,
)
from gwproto.message import Message
from scada_app import ScadaApp

BUS_NAME = "i2c-bus"
REQUESTER = "gw108-thermistor-reader"


class FakeSMBus:
    """Byte-level register store; block ops mirror the big-endian contract."""

    def __init__(self) -> None:
        self.bytes: dict[tuple[int, int], int] = {}
        self.bare_bytes: dict[int, int] = {}
        self.raise_on: set[str] = set()

    def write_byte(self, addr: int, value: int) -> None:
        self._check("write_byte")
        self.bare_bytes[addr] = value

    def _check(self, op: str) -> None:
        if op in self.raise_on:
            raise OSError(f"simulated {op} failure")

    def read_byte_data(self, addr: int, reg: int) -> int:
        self._check("read_byte_data")
        return self.bytes.get((addr, reg), 0)

    def write_byte_data(self, addr: int, reg: int, value: int) -> None:
        self._check("write_byte_data")
        self.bytes[(addr, reg)] = value

    def write_i2c_block_data(self, addr: int, reg: int, data: list[int]) -> None:
        self._check("write_i2c_block_data")
        for i, b in enumerate(data):
            self.bytes[(addr, reg + i)] = b

    def read_i2c_block_data(self, addr: int, reg: int, n: int) -> list[int]:
        self._check("read_i2c_block_data")
        return [self.bytes.get((addr, reg + i), 0) for i in range(n)]


@pytest.fixture
def bus_app(tmp_path: Path) -> ScadaApp:
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
    settings.paths.hardware_layout = layout_path
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.fixture
def bus(bus_app: ScadaApp) -> I2cBus:
    actor = I2cBus(BUS_NAME, bus_app)
    actor.is_simulated = False
    actor.i2c = FakeSMBus()
    actor.sent: list[tuple[str, I2cResult]] = []
    actor._send_to = lambda dst, payload, src=None: actor.sent.append(
        (dst.name, payload)
    )
    return actor


def message(payload) -> Message:
    return Message(Src=REQUESTER, Dst=BUS_NAME, Payload=payload)


def trigger() -> str:
    return str(uuid.uuid4())


def test_registered_actor_instantiates(bus_app: ScadaApp) -> None:
    node = bus_app.hardware_layout.node(BUS_NAME)
    assert node is not None
    assert BUS_NAME in bus_app.raw_proactor.get_communicator_names()


def test_write_bit_read_modify_write(bus: I2cBus) -> None:
    bus.i2c.bytes[(0x20, 0x02)] = 0b0100_0001
    result = bus.process_message(
        message(
            I2cWriteBit(
                Bus=BUS_NAME,
                Address=I2cBitAddress(I2cAddress=0x20, RegisterIndex=0x02, BitIndex=3),
                Value=1,
                TriggerId=trigger(),
            )
        )
    )
    assert result.is_ok()
    assert bus.i2c.bytes[(0x20, 0x02)] == 0b0100_1001
    dst, reply = bus.sent[-1]
    assert dst == REQUESTER
    assert reply.Success and reply.Value == 1
    assert reply.Operation == I2cOperation.WriteBit


def test_read_bit(bus: I2cBus) -> None:
    bus.i2c.bytes[(0x21, 0x00)] = 0b0000_0100
    tid = trigger()
    bus.process_message(
        message(
            I2cReadBit(
                Bus=BUS_NAME,
                Address=I2cBitAddress(I2cAddress=0x21, RegisterIndex=0x00, BitIndex=2),
                TriggerId=tid,
            )
        )
    )
    _, reply = bus.sent[-1]
    assert reply.Success and reply.Value == 1
    assert reply.TriggerId == tid


def test_reg_word_ops_are_big_endian(bus: I2cBus) -> None:
    # ADS1115 config-style word: 0x8583 must land high byte first
    bus.process_message(
        message(
            I2cWriteReg(
                Bus=BUS_NAME,
                Address=I2cRegAddress(I2cAddress=0x49, RegisterIndex=0x01),
                NumBytes=2,
                Value=0x8583,
                TriggerId=trigger(),
            )
        )
    )
    assert bus.i2c.bytes[(0x49, 0x01)] == 0x85
    assert bus.i2c.bytes[(0x49, 0x02)] == 0x83

    bus.process_message(
        message(
            I2cReadReg(
                Bus=BUS_NAME,
                Address=I2cRegAddress(I2cAddress=0x49, RegisterIndex=0x01),
                NumBytes=2,
                TriggerId=trigger(),
            )
        )
    )
    _, reply = bus.sent[-1]
    assert reply.Success and reply.Value == 0x8583
    assert reply.Operation == I2cOperation.ReadReg


def test_failure_reports_error_not_crash(bus: I2cBus) -> None:
    bus.i2c.raise_on.add("read_i2c_block_data")
    result = bus.process_message(
        message(
            I2cReadReg(
                Bus=BUS_NAME,
                Address=I2cRegAddress(I2cAddress=0x49, RegisterIndex=0x00),
                NumBytes=2,
                TriggerId=trigger(),
            )
        )
    )
    assert result.is_ok()
    _, reply = bus.sent[-1]
    assert not reply.Success
    assert reply.Value is None
    assert "read_i2c_block_data" in reply.Error


def test_write_byte_is_register_less(bus: I2cBus) -> None:
    bus.process_message(
        message(
            I2cWriteByte(
                Bus=BUS_NAME, I2cAddress=0x70, Value=0x04, TriggerId=trigger()
            )
        )
    )
    assert bus.i2c.bare_bytes[0x70] == 0x04
    assert bus.i2c.bytes == {}  # no register write happened
    _, reply = bus.sent[-1]
    assert reply.Success and reply.Value == 0x04
    assert reply.Operation == I2cOperation.WriteByte


def test_read_bytes_via_sim_backend(bus: I2cBus) -> None:
    # the bare sequential receive has a sim-native implementation; drive
    # the mux + DAC model end to end through bus ops
    bus.i2c = SimI2c(
        mux_address=0x70, dac_address=0x60, dac_mux_channels=(2,)
    )
    bus.i2c.dacs[2].eeprom[0] = [123, 1, 0]
    bus.process_message(
        message(
            I2cWriteByte(
                Bus=BUS_NAME, I2cAddress=0x70, Value=1 << 2, TriggerId=trigger()
            )
        )
    )
    bus.process_message(
        message(
            I2cReadBytes(
                Bus=BUS_NAME,
                I2cAddress=0x60,
                NumBytes=mcp4728.READ_LEN,
                TriggerId=trigger(),
            )
        )
    )
    _, reply = bus.sent[-1]
    assert reply.Success and reply.Operation == I2cOperation.ReadBytes
    assert reply.Value is None and len(reply.Bytes) == mcp4728.READ_LEN
    hi, lo = mcp4728.eeprom_data(reply.Bytes, 0)
    assert mcp4728.decode_data(hi, lo) == (123, 1, 0)


def test_wrong_bus_name_rejected(bus: I2cBus) -> None:
    bus.process_message(
        message(
            I2cReadBit(
                Bus="some-other-bus",
                Address=I2cBitAddress(I2cAddress=0x20, RegisterIndex=0, BitIndex=0),
                TriggerId=trigger(),
            )
        )
    )
    _, reply = bus.sent[-1]
    assert not reply.Success
    assert "some-other-bus" in reply.Error


def test_unknown_requester_is_err(bus: I2cBus) -> None:
    result = bus.process_message(
        Message(
            Src="not-a-node",
            Dst=BUS_NAME,
            Payload=I2cReadBit(
                Bus=BUS_NAME,
                Address=I2cBitAddress(I2cAddress=0x20, RegisterIndex=0, BitIndex=0),
                TriggerId=trigger(),
            ),
        )
    )
    assert result.is_err()
