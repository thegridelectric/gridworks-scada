"""I2cDacWriter tests: layout resolution (DacName against the board
record), the mux+DAC write choreography run through the REAL I2cBus actor
over the SimI2c register model, Multi-Write-only routine assertion (EEPROM
untouched), the boot EEPROM verify (mismatch → reprogram → re-verify), and
failure containment (a bus fault becomes a throttled Glitch, never a
crash).

The spruce artifact carries the Dac2 writer component and its
`gw108-dac2-writer` node natively (emitted since the tlayouts snapshot
reseeded on actor.class 013).
"""

import asyncio
from pathlib import Path

import pytest

from actors.i2c_bus import I2cBus
from actors.i2c_dac_writer import I2cDacWriter
from gwproto.message import Message
from scada_app import ScadaApp

SPRUCE_LAYOUT = Path(__file__).parent.parent / "config" / "gw.nolan.layout.json"
SPRUCE_OPS = (
    Path(__file__).parent.parent
    / "config"
    / "gw.nolan.operational.params.json"
)
DAC_NODE = "gw108-dac2-writer"
BUS_NAME = "i2c-bus"
MUX_ADDRESS = 0x70
DAC_ADDRESS = 0x60
DAC2_MUX_CHANNEL = 2
CHANNEL_C = 2
C_RAW = 3020  # the layout's PowerOnRawValue for channel C (7.55 V)


@pytest.fixture
def rig() -> tuple[I2cDacWriter, I2cBus]:
    settings = ScadaApp.get_settings()
    settings.is_simulated = True
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    settings.paths.operational_params = SPRUCE_OPS
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()

    bus = I2cBus(BUS_NAME, app)
    writer = I2cDacWriter(DAC_NODE, app)
    writer.warnings = []
    writer.send_warning = lambda summary, details="": writer.warnings.append(
        summary
    )

    # direct cross-wiring: writer ops run the real bus handler; bus replies
    # resolve the writer's pending futures
    writer._send_to = lambda dst, payload, src=None: bus.process_message(
        Message(Src=DAC_NODE, Dst=BUS_NAME, Payload=payload)
    )
    bus._send_to = lambda dst, payload, src=None: (
        writer.process_message(
            Message(Src=BUS_NAME, Dst=DAC_NODE, Payload=payload)
        )
        if dst.name == DAC_NODE
        else None
    )
    return writer, bus


def test_registered_actor_instantiates(rig: tuple[I2cDacWriter, I2cBus]) -> None:
    writer, _ = rig
    node = writer.layout.node(DAC_NODE)
    assert node is not None
    assert node.component is writer.component


def test_resolves_from_board_record(rig: tuple[I2cDacWriter, I2cBus]) -> None:
    writer, _ = rig
    assert writer.dac_address == DAC_ADDRESS
    assert writer.mux_address == MUX_ADDRESS
    assert writer.mux_channel == DAC2_MUX_CHANNEL
    assert set(writer.configs) == {0, 1, 2, 3}
    assert writer.configs[CHANNEL_C].PowerOnRawValue == C_RAW


def test_assert_targets_is_multi_write_only(
    rig: tuple[I2cDacWriter, I2cBus],
) -> None:
    writer, bus = rig
    dac = bus.i2c.dacs[DAC2_MUX_CHANNEL]
    asyncio.run(writer._assert_targets())
    assert dac.register[CHANNEL_C] == [C_RAW, 1, 0]
    assert dac.register[0] == [0, 1, 0]
    # Multi-Write never touches EEPROM — the wear/default-clobber guard
    assert dac.eeprom[CHANNEL_C] == [0, 0, 0]
    assert not writer.warnings


def test_boot_verify_reprograms_then_stays_clean(
    rig: tuple[I2cDacWriter, I2cBus],
) -> None:
    writer, bus = rig
    dac = bus.i2c.dacs[DAC2_MUX_CHANNEL]
    assert asyncio.run(writer._verify_eeprom())
    assert dac.eeprom[CHANNEL_C] == [C_RAW, 1, 0]
    assert dac.register[CHANNEL_C] == [C_RAW, 1, 0]
    assert writer.warnings == ["i2c-dac-eeprom-reprogrammed"]
    # a chip already carrying the declared defaults verifies silently
    writer.warnings.clear()
    assert asyncio.run(writer._verify_eeprom())
    assert writer.warnings == []


def test_bus_fault_contained_throttled_and_heals(
    rig: tuple[I2cDacWriter, I2cBus],
) -> None:
    writer, bus = rig
    bus.i2c.inject_fault(MUX_ADDRESS, count=None)
    asyncio.run(writer._assert_targets())
    assert writer.warnings == ["i2c-dac-write-failed"] * 4
    asyncio.run(writer._assert_targets())
    assert len(writer.warnings) == 4  # once per failure streak
    bus.i2c.clear_faults()
    asyncio.run(writer._assert_targets())
    assert bus.i2c.dacs[DAC2_MUX_CHANNEL].register[CHANNEL_C] == [C_RAW, 1, 0]
    bus.i2c.inject_fault(MUX_ADDRESS, count=None)
    asyncio.run(writer._assert_targets())
    assert len(writer.warnings) == 8  # a new streak warns again


def test_verify_read_failure_warns_and_returns_false(
    rig: tuple[I2cDacWriter, I2cBus],
) -> None:
    writer, bus = rig
    bus.i2c.inject_fault(DAC_ADDRESS, count=None)
    assert not asyncio.run(writer._verify_eeprom())
    assert writer.warnings == ["i2c-dac-eeprom-read-failed"]
