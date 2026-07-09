from gwsproto.enums import DeviceType, RelayWiringConfig, TelemetryName
from gwsproto.named_types.i2c_bus import I2cBus
from gwsproto.named_types.i2c_expander import I2cExpander
from gwsproto.named_types.i2c_relay_capability import I2cRelayCapability
from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt

# The GridWorks relay panel: two 16-channel Krida boards (PCF8575 expanders)
# assembled and labeled as one device, markings Relay1-Relay32. Each board's
# I²C address is DIP-switch-selectable in the field (PCF8575: 0x20-0x27); the
# chosen addresses are a deployment fact on the component's I2cAddressList,
# index-aligned with Expanders.
DEFAULT_BUS = "DefaultBus"

_ALLOWED_ADDRESSES = list(range(0x20, 0x28))

_ALL_WIRINGS = [
    RelayWiringConfig.NormallyClosed,
    RelayWiringConfig.NormallyOpen,
    RelayWiringConfig.DoubleThrow,
]


def _pin(marking: int) -> int:
    """PCF8575 pin for a panel marking's board-local position. The panel's
    first bank of eight is wired in reverse order (marking 1 -> pin 7, ...,
    8 -> pin 0); the second bank is direct (9 -> pin 8, ..., 16 -> pin 15)."""
    i = (marking - 1) % 16 + 1
    position = 9 - i if i < 9 else i
    return position - 1


def _relay(marking: int) -> I2cRelayCapability:
    pin = _pin(marking)
    return I2cRelayCapability(
        RelayName=f"Relay{marking}",
        ExpanderIdx=(marking - 1) // 16 + 1,
        RegisterIndex=pin // 8,
        BitIndex=pin % 8,
        SupportedWiringConfigs=_ALL_WIRINGS,
    )


krida_double_relay_board_16_device_type = ScadaDeviceTypeGt(
    DeviceType=DeviceType.KridaDoubleRelayBoard16.value,
    DisplayName="GridWorks relay panel: two 16-channel Krida boards, markings Relay1-Relay32",
    MinPollPeriodMs=200,
    TelemetryNameList=[TelemetryName.RelayState],
    BusList=[
        I2cBus(Name=DEFAULT_BUS, BusNumber=1),
    ],
    Expanders=[
        I2cExpander(
            ExpanderIdx=1, I2cBus=DEFAULT_BUS, AllowedI2cAddressList=_ALLOWED_ADDRESSES
        ),
        I2cExpander(
            ExpanderIdx=2, I2cBus=DEFAULT_BUS, AllowedI2cAddressList=_ALLOWED_ADDRESSES
        ),
    ],
    I2cRelays=[_relay(marking) for marking in range(1, 33)],
)
