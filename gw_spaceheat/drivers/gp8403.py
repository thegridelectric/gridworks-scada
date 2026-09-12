"""GP8403 dual-DAC wire constants (the DFRobot DFR0971 module).

Two 12-bit channels, each written as one little-endian word to its output
register with the code in the top twelve bits; the range register selects
0-5 V or 0-10 V once at init. The chip has no readable configuration and
stores no power-on value: an output sits at the chip default after power-up
until the first write.
"""

RANGE_REG = 0x01
RANGE_10V = 0x11
OUTPUT_REG = (0x02, 0x04)  # channel 0, channel 1
CODES = 4096
FULL_SCALE_VOLTS = 10.0
SUPPORTS_POWER_ON_STORE = False


def encode_word(code: int) -> int:
    """The register word carrying a 12-bit code (code in bits 4-15)."""
    return (code & 0x0FFF) << 4
