"""MCP4728 quad-DAC wire constants and data-byte codec.

Command bytes address one of the four channels; the two data bytes carry
VREF / gain configuration plus the 12-bit value. Multi-Write touches only
the channel's input register; Single Write programs the input register AND
the channel's EEPROM (the power-on default) — EEPROM writes are a
provisioning act, never a routine assertion (endurance is finite and each
write busies the chip). The chip's read protocol is a bare 24-byte
sequential receive with no register pointer: per channel, three bytes of
input register then three bytes of EEPROM.
"""

MULTI_WRITE_BASE = 0x40  # input register only
SINGLE_WRITE_BASE = 0x58  # input register AND EEPROM
READ_LEN = 24  # 4 channels x (3 input-register bytes + 3 EEPROM bytes)

VREF_BIT = {"Internal": 1, "Vdd": 0}


def command(base: int, channel: int) -> int:
    """The command byte addressing `channel` (0-3) in the given family."""
    return base | ((channel & 0x03) << 1)


def gain_bit(power_on_gain: int) -> int:
    """The GX bit for a declared gain of 1 or 2."""
    return 0 if power_on_gain == 1 else 1


def encode_data(value: int, vref: int, gain: int) -> tuple[int, int]:
    """(hi, lo) data bytes for a 12-bit value with VREF/GX bits (PD 00)."""
    return (vref << 7) | (gain << 4) | ((value >> 8) & 0x0F), value & 0xFF


def decode_data(hi: int, lo: int) -> tuple[int, int, int]:
    """(value, vref, gain) from the two data bytes; PD bits ignored."""
    return ((hi & 0x0F) << 8) | lo, (hi >> 7) & 0x01, (hi >> 4) & 0x01


def eeprom_data(read: list[int], channel: int) -> tuple[int, int]:
    """The (hi, lo) data bytes of `channel`'s EEPROM triplet in a full
    24-byte read (each triplet's first byte is chip status)."""
    base = channel * 6 + 3
    return read[base + 1], read[base + 2]
