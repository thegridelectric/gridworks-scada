"""Fake-chip i2c backend: the register-level fidelity dial.

Presents the smbus2 subset the I2cBus actor uses (byte + big-endian block
ops) over a per-address register store, so the real relay/bus/reader actors
run their genuine choreography against a fake board. Addresses registered as
TCA9555 expanders get chip-faithful semantics: power-on-reset defaults
(outputs 0xFF, config 0xFF = all inputs), and input ports that mirror the
output flip-flops ONLY where the config register says output — a floating
(input-configured) pin reads the float level, which is how the 07-16 field
incident's "writes read back fine while pins float" behavior reproduces.

Fault injection is the chaos lever: EIO per address (transient count or
permanent) and garbled reads (bit-flipped data for N reads).
"""

from errno import EIO

from drivers import tca9555


class SimTca9555:
    """One expander's register file with chip-faithful input-port reads."""

    FLOAT_LEVEL = 0

    def __init__(self) -> None:
        self.power_on_reset()

    def power_on_reset(self) -> None:
        self.registers: dict[int, int] = {
            tca9555.INPUT_PORT_0: 0x00,
            tca9555.INPUT_PORT_1: 0x00,
            tca9555.OUTPUT_PORT_0: 0xFF,
            tca9555.OUTPUT_PORT_1: 0xFF,
            4: 0x00,  # polarity inversion ports, untouched by our code
            5: 0x00,
            tca9555.CONFIG_PORT_0: 0xFF,
            tca9555.CONFIG_PORT_1: 0xFF,
        }

    def read(self, register: int) -> int:
        if register in (tca9555.INPUT_PORT_0, tca9555.INPUT_PORT_1):
            output = self.registers[register + 2]
            config = self.registers[register + 6]
            float_byte = 0xFF if self.FLOAT_LEVEL else 0x00
            # configured-as-output bits (config 0) mirror the flip-flop;
            # input-configured bits (config 1) read the float level
            return (output & ~config & 0xFF) | (float_byte & config)
        return self.registers.get(register, 0)

    def write(self, register: int, value: int) -> None:
        if register in (tca9555.INPUT_PORT_0, tca9555.INPUT_PORT_1):
            return  # input ports are read-only on the chip
        self.registers[register] = value & 0xFF


class SimI2c:
    """smbus2-surface fake bus: SimTca9555 at expander addresses, a plain
    register store elsewhere. Not thread-safe; the I2cBus actor serializes."""

    def __init__(self, expander_addresses: tuple[int, ...] = ()) -> None:
        self.expanders: dict[int, SimTca9555] = {
            addr: SimTca9555() for addr in expander_addresses
        }
        self.registers: dict[tuple[int, int], int] = {}
        # address -> remaining EIO count; None = fail until cleared
        self._faults: dict[int, int | None] = {}
        # address -> remaining garbled-read count
        self._garbles: dict[int, int] = {}

    # ---- fault injection ----

    def inject_fault(self, address: int, count: int | None = None) -> None:
        """Ops on the address raise EIO `count` times (None = until
        clear_faults) — the dac3 failure shapes."""
        self._faults[address] = count

    def inject_read_garble(self, address: int, count: int = 1) -> None:
        """The next `count` reads on the address return bit-flipped data —
        the single-garbled-read shape the confirm re-read guard exists for."""
        self._garbles[address] = count

    def clear_faults(self) -> None:
        self._faults.clear()
        self._garbles.clear()

    def power_on_reset(self, address: int) -> None:
        """Simulate the OPS-452 mid-run reset on one expander."""
        self.expanders[address].power_on_reset()

    # ---- fault plumbing ----

    def _check_fault(self, address: int) -> None:
        if address not in self._faults:
            return
        remaining = self._faults[address]
        if remaining is None:
            raise OSError(EIO, "simulated permanent i2c fault")
        if remaining > 0:
            self._faults[address] = remaining - 1
            raise OSError(EIO, "simulated transient i2c fault")
        del self._faults[address]

    def _garble(self, address: int, value: int) -> int:
        remaining = self._garbles.get(address, 0)
        if remaining > 0:
            self._garbles[address] = remaining - 1
            return value ^ 0xFF
        return value

    # ---- the smbus2 subset the I2cBus actor uses ----

    def read_byte_data(self, address: int, register: int) -> int:
        self._check_fault(address)
        if address in self.expanders:
            value = self.expanders[address].read(register)
        else:
            value = self.registers.get((address, register), 0)
        return self._garble(address, value)

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        self._check_fault(address)
        if address in self.expanders:
            self.expanders[address].write(register, value)
        else:
            self.registers[(address, register)] = value & 0xFF

    def read_i2c_block_data(
        self, address: int, register: int, length: int
    ) -> list[int]:
        self._check_fault(address)
        if address in self.expanders:
            values = [
                self.expanders[address].read(register + i)
                for i in range(length)
            ]
        else:
            values = [
                self.registers.get((address, register + i), 0)
                for i in range(length)
            ]
        return [self._garble(address, v) for v in values]

    def write_i2c_block_data(
        self, address: int, register: int, data: list[int]
    ) -> None:
        self._check_fault(address)
        if address in self.expanders:
            for i, value in enumerate(data):
                self.expanders[address].write(register + i, value)
        else:
            for i, value in enumerate(data):
                self.registers[(address, register + i)] = value & 0xFF
