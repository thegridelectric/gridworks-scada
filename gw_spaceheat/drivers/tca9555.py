"""TCA9555 GPIO-expander register map.

Shared by every actor that drives or reads a TCA9555 through the I2cBus bit
ops. The chip exposes three register pairs, one register per 8-bit port:
input ports 0/1 (the actual level at each pin, readable even when the pin is
configured as an output), output ports 2/3 (the driven level), and
configuration ports 6/7 (1 = input, 0 = output; power-on reset leaves every
pin an input — the OPS-452 reset signature). Board records declare relay
positions by OUTPUT register index; the input and configuration registers
for the same port are fixed offsets from it.
"""

INPUT_PORT_0 = 0
INPUT_PORT_1 = 1
OUTPUT_PORT_0 = 2
OUTPUT_PORT_1 = 3
CONFIG_PORT_0 = 6
CONFIG_PORT_1 = 7

_OUTPUT_REGISTERS = (OUTPUT_PORT_0, OUTPUT_PORT_1)


def input_register(output_register: int) -> int:
    """The input-port register reading the actual pin levels of the port
    driven by the given output register."""
    if output_register not in _OUTPUT_REGISTERS:
        raise ValueError(f"{output_register} is not a TCA9555 output register")
    return output_register - 2


def config_register(output_register: int) -> int:
    """The configuration register governing the port driven by the given
    output register."""
    if output_register not in _OUTPUT_REGISTERS:
        raise ValueError(f"{output_register} is not a TCA9555 output register")
    return output_register + 4
