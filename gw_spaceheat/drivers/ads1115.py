"""ADS1115 register-level constants + conversion choreography facts.

Shared by every actor that reads an ADS1115 through the I2cBus reg ops: write
CONFIG_REG with config_word(channel) (2 bytes, big-endian), wait
CONVERSION_WAIT_S, then read CONVERSION_REG (2 bytes) and convert via
volts_from_raw. PGA fixed at ±4.096 V, 128 SPS single-shot — the smallest
full-scale that spans the gw108's 3.3 V divider/CT circuits, and the data
rate the deployed blinka path used.
"""

CONVERSION_REG = 0x00
CONFIG_REG = 0x01

FULL_SCALE_VOLTS = 4.096
CONVERSION_WAIT_S = 0.012  # one 128 SPS conversion (7.8 ms) + settle margin

_MUX_BY_CHANNEL = {"P0": 0b100, "P1": 0b101, "P2": 0b110, "P3": 0b111}

_OS_SINGLE = 0x8000
_PGA_4V096 = 0b001 << 9
_MODE_SINGLE = 0x0100
_DR_128SPS = 0b100 << 5
_COMP_DISABLE = 0b00011


def config_word(adc_channel: str) -> int:
    """The 16-bit CONFIG_REG value that starts a single-shot conversion of
    AIN<n> vs GND, for blinka-style channel names P0..P3."""
    mux = _MUX_BY_CHANNEL[adc_channel]
    return (
        _OS_SINGLE
        | (mux << 12)
        | _PGA_4V096
        | _MODE_SINGLE
        | _DR_128SPS
        | _COMP_DISABLE
    )


def volts_from_raw(raw: int) -> float:
    """Signed 16-bit conversion-register value to volts at ±4.096 V PGA."""
    if raw > 0x7FFF:
        raw -= 0x10000
    return raw * FULL_SCALE_VOLTS / 32768
