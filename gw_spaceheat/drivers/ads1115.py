"""ADS1115 register-level constants + conversion choreography facts.

Shared by every actor that reads an ADS1115 through the I2cBus reg ops: write
CONFIG_REG with config_word(channel, data_rate_sps) (2 bytes, big-endian),
wait conversion_wait_s(data_rate_sps), then read CONVERSION_REG (2 bytes) and
convert via volts_from_raw. PGA fixed at ±4.096 V single-shot — the smallest
full-scale that spans the gw108's 3.3 V divider/CT circuits. The data rate is
declared by the consuming component (the thermistor reader's DataRateSps, a
member of the board ADC's SupportedDataRatesSps) and rides in the config word
of every conversion — the chip holds nothing persistent.
"""

CONVERSION_REG = 0x00
CONFIG_REG = 0x01

FULL_SCALE_VOLTS = 4.096

_MUX_BY_CHANNEL = {"P0": 0b100, "P1": 0b101, "P2": 0b110, "P3": 0b111}

_OS_SINGLE = 0x8000
_PGA_4V096 = 0b001 << 9
_MODE_SINGLE = 0x0100
_COMP_DISABLE = 0b00011

_DR_BITS_BY_SPS = {
    8: 0b000,
    16: 0b001,
    32: 0b010,
    64: 0b011,
    128: 0b100,
    250: 0b101,
    475: 0b110,
    860: 0b111,
}

_SETTLE_MARGIN_S = 0.004


def config_word(adc_channel: str, data_rate_sps: int) -> int:
    """The 16-bit CONFIG_REG value that starts a single-shot conversion of
    AIN<n> vs GND, for blinka-style channel names P0..P3 at one of the
    chip's eight data rates."""
    mux = _MUX_BY_CHANNEL[adc_channel]
    return (
        _OS_SINGLE
        | (mux << 12)
        | _PGA_4V096
        | _MODE_SINGLE
        | (_DR_BITS_BY_SPS[data_rate_sps] << 5)
        | _COMP_DISABLE
    )


def conversion_wait_s(data_rate_sps: int) -> float:
    """One conversion (1/SPS) plus settle margin."""
    return 1.0 / data_rate_sps + _SETTLE_MARGIN_S


def volts_from_raw(raw: int) -> float:
    """Signed 16-bit conversion-register value to volts at ±4.096 V PGA."""
    if raw > 0x7FFF:
        raw -= 0x10000
    return raw * FULL_SCALE_VOLTS / 32768
