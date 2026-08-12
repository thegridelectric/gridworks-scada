"""Unit tests for the SimI2c fake-chip backend (drivers/sim_i2c.py)."""

import pytest

from drivers import tca9555
from drivers.sim_i2c import SimI2c

EXPANDER = 0x20


@pytest.fixture
def sim() -> SimI2c:
    return SimI2c(expander_addresses=(EXPANDER,))


def test_por_defaults(sim: SimI2c) -> None:
    assert sim.read_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0) == 0xFF
    assert sim.read_byte_data(EXPANDER, tca9555.CONFIG_PORT_0) == 0xFF


def test_input_mirrors_output_only_when_configured(sim: SimI2c) -> None:
    # POR: config all-inputs — outputs hold 0xFF but pins float (read 0)
    assert sim.read_byte_data(EXPANDER, tca9555.INPUT_PORT_0) == 0x00
    # configure port 0 as outputs: input now mirrors the flip-flops
    sim.write_byte_data(EXPANDER, tca9555.CONFIG_PORT_0, 0x00)
    sim.write_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0, 0b0000_0101)
    assert sim.read_byte_data(EXPANDER, tca9555.INPUT_PORT_0) == 0b0000_0101
    # flip one bit back to input: that pin floats while the rest mirror —
    # the 07-16 "writes read back fine while pins float" shape per-bit
    sim.write_byte_data(EXPANDER, tca9555.CONFIG_PORT_0, 0b0000_0001)
    assert sim.read_byte_data(EXPANDER, tca9555.INPUT_PORT_0) == 0b0000_0100


def test_input_ports_are_read_only(sim: SimI2c) -> None:
    sim.write_byte_data(EXPANDER, tca9555.INPUT_PORT_0, 0xAB)
    assert sim.read_byte_data(EXPANDER, tca9555.INPUT_PORT_0) == 0x00


def test_transient_fault_counts_down(sim: SimI2c) -> None:
    sim.inject_fault(EXPANDER, count=2)
    for _ in range(2):
        with pytest.raises(OSError):
            sim.read_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0)
    assert sim.read_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0) == 0xFF


def test_permanent_fault_until_cleared(sim: SimI2c) -> None:
    sim.inject_fault(EXPANDER, count=None)
    for _ in range(3):
        with pytest.raises(OSError):
            sim.write_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0, 0x00)
    sim.clear_faults()
    sim.write_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0, 0x00)
    assert sim.read_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0) == 0x00


def test_garbled_read_flips_once(sim: SimI2c) -> None:
    sim.inject_read_garble(EXPANDER, count=1)
    assert sim.read_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0) == 0x00  # ~0xFF
    assert sim.read_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0) == 0xFF


def test_non_expander_addresses_are_plain_registers(sim: SimI2c) -> None:
    sim.write_i2c_block_data(0x49, 0x01, [0x85, 0x83])
    assert sim.read_i2c_block_data(0x49, 0x01, 2) == [0x85, 0x83]


def test_power_on_reset_restores_por(sim: SimI2c) -> None:
    sim.write_byte_data(EXPANDER, tca9555.CONFIG_PORT_0, 0x00)
    sim.write_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0, 0x01)
    sim.power_on_reset(EXPANDER)
    assert sim.read_byte_data(EXPANDER, tca9555.CONFIG_PORT_0) == 0xFF
    assert sim.read_byte_data(EXPANDER, tca9555.OUTPUT_PORT_0) == 0xFF
