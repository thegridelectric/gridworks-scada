from gwsproto.enums import DeviceType, I2cAdcType, I2cDacType, RelayWiringConfig
from gwsproto.named_types.i2c_adc_config import I2cAdcConfig
from gwsproto.named_types.i2c_bit_address import I2cBitAddress
from gwsproto.named_types.i2c_bus import I2cBus
from gwsproto.named_types.i2c_dac_config import I2cDacConfig
from gwsproto.named_types.i2c_relay_config import I2cRelayConfig
from gwsproto.named_types.i2c_thermistor_interface_config import (
    I2cThermistorInterfaceConfig,
)
from gwsproto.named_types.native_gpio_pin import NativeGpioPin
from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt

# QUESTION FOR JESSICA: the gw108's I²C peripherals (GPIO expanders 0x20/0x21,
# ADCs 0x48/0x49, DAC 0x60) are all placed on one bus "DefaultBus" -> /dev/i2c-1
# here. If the board actually splits these across more than one physical bus,
# add the extra I2cBus entries and repoint each config's I2cBus name.
DEFAULT_BUS = "DefaultBus"


def _relay(
    i2c_address: int,
    register: int,
    bit: int,
    *wiring: RelayWiringConfig,
    name: str,
    notes: str | None = None,
) -> I2cRelayConfig:
    return I2cRelayConfig(
        RelayName=name,
        I2cBus=DEFAULT_BUS,
        Address=I2cBitAddress(
            I2cAddress=i2c_address, RegisterIndex=register, BitIndex=bit
        ),
        SupportedWiringConfigs=list(wiring),
        Notes=notes,
    )


gw108_device_type = ScadaDeviceTypeGt(
    DeviceType=DeviceType.GridworksScadaGw108.value,
    TelemetryNameList=[],  # FIX
    BusList=[
        I2cBus(Name=DEFAULT_BUS, BusNumber=1),
    ],
    NativeGpioInputs=[
        NativeGpioPin(Name="Zone1Whitewire", BcmPin=17),
        NativeGpioPin(Name="Zone2Whitewire", BcmPin=27),
        NativeGpioPin(Name="Zone3Whitewire", BcmPin=22),
        NativeGpioPin(Name="Zone4Whitewire", BcmPin=10),
        NativeGpioPin(Name="Zone5Whitewire", BcmPin=9),
        NativeGpioPin(Name="Zone6Whitewire", BcmPin=11),
        NativeGpioPin(Name="Shutdown", BcmPin=18),
    ],
    NativeGpioOutputs=[
        NativeGpioPin(Name="TstatPower", BcmPin=4),
        NativeGpioPin(Name="Vdc", BcmPin=23),
        NativeGpioPin(Name="Watchdog", BcmPin=24),
        NativeGpioPin(Name="PowerOff", BcmPin=25),
    ],
    I2cRelays=[
        _relay(0x20, 2, 0, RelayWiringConfig.DoubleThrow, name="Zone1Failsafe"),
        _relay(0x20, 2, 1, RelayWiringConfig.DoubleThrow, name="Zone2Failsafe"),
        _relay(0x20, 2, 2, RelayWiringConfig.DoubleThrow, name="Zone3Failsafe"),
        _relay(0x20, 2, 3, RelayWiringConfig.DoubleThrow, name="Zone4Failsafe"),
        _relay(0x20, 2, 4, RelayWiringConfig.DoubleThrow, name="Zone5Failsafe"),
        _relay(0x20, 2, 5, RelayWiringConfig.DoubleThrow, name="Zone6Failsafe"),
        _relay(0x20, 3, 0, RelayWiringConfig.NormallyOpen, name="Zone1Scada"),
        _relay(0x20, 3, 1, RelayWiringConfig.NormallyOpen, name="Zone2Scada"),
        _relay(0x20, 3, 2, RelayWiringConfig.NormallyOpen, name="Zone3Scada"),
        _relay(0x20, 3, 3, RelayWiringConfig.NormallyOpen, name="Zone4Scada"),
        _relay(0x20, 3, 4, RelayWiringConfig.NormallyOpen, name="Zone5Scada"),
        _relay(0x20, 3, 5, RelayWiringConfig.NormallyOpen, name="Zone6Scada"),
        _relay(
            0x21,
            2,
            1,
            RelayWiringConfig.NormallyOpen,
            name="BufferTop",
            notes="Upper buffer resistive heating element",
        ),
        _relay(
            0x21,
            2,
            2,
            RelayWiringConfig.NormallyOpen,
            name="BufferBottom",
            notes="Lower buffer resistive heating element",
        ),
        _relay(
            0x21,
            3,
            6,
            RelayWiringConfig.NormallyOpen,
            name="StoreTop",
            notes="Upper buffer resistive heating element",
        ),
        _relay(
            0x21,
            3,
            7,
            RelayWiringConfig.NormallyOpen,
            name="StoreBottom",
            notes="Lower buffer resistive heating element",
        ),
        _relay(
            0x21,
            2,
            0,
            RelayWiringConfig.NormallyOpen,
            name="HeatPumpEnable",
            notes="??",
        ),
        _relay(
            0x21,
            2,
            3,
            RelayWiringConfig.DoubleThrow,
            name="BoilerBufferValve",
            notes="??",
        ),
        _relay(
            0x21,
            2,
            4,
            RelayWiringConfig.NormallyClosed,
            name="BoilerIntercept",
            notes="By default, signal goes to boiler. ",
        ),
        _relay(0x21, 2, 7, RelayWiringConfig.NormallyOpen, name="PrimaryPump"),
        _relay(0x21, 3, 5, RelayWiringConfig.NormallyOpen, name="SecondaryPump"),
        _relay(0x21, 3, 4, RelayWiringConfig.NormallyOpen, name="StorePump"),
        _relay(0x21, 3, 3, RelayWiringConfig.DoubleThrow, name="DischargeValve"),
        _relay(0x21, 3, 2, RelayWiringConfig.DoubleThrow, name="IsoValve"),
        _relay(0x21, 3, 1, RelayWiringConfig.DoubleThrow, name="IsoValveFailsafe"),
        _relay(
            0x21,
            3,
            0,
            RelayWiringConfig.NormallyOpen,
            RelayWiringConfig.NormallyClosed,
            RelayWiringConfig.DoubleThrow,
            name="FcmMisc",
        ),
        _relay(
            0x21,
            2,
            5,
            RelayWiringConfig.NormallyOpen,
            RelayWiringConfig.NormallyClosed,
            RelayWiringConfig.DoubleThrow,
            name="Misc1",
        ),
        _relay(
            0x21,
            2,
            6,
            RelayWiringConfig.NormallyOpen,
            RelayWiringConfig.NormallyClosed,
            RelayWiringConfig.DoubleThrow,
            name="Misc2",
        ),
    ],
    CtAdc=I2cAdcConfig(
        Name="Ct",
        I2cBus=DEFAULT_BUS,
        I2cAddress=0x48,
        AdcType=I2cAdcType.Ads1115,
        Channels=4,
    ),
    ThermistorAdcs=[
        I2cThermistorInterfaceConfig(
            Name="Thermistors",
            I2cBus=DEFAULT_BUS,
            I2cAddress=0x49,
            AdcType=I2cAdcType.Ads1115,
            # QUESTION FOR JESSICA: AdcReferenceVolts is the divider's pull-up
            # supply voltage — 3.3 assumed; confirm the gw108 value. The old
            # PullupResistorKOhms=5.65 maps to SeriesResistanceKOhms here.
            AdcReferenceVolts=3.3,
            SeriesResistanceKOhms=5.65,
        )
    ],
    Dacs=[
        I2cDacConfig(
            DacName="Zones",
            I2cBus=DEFAULT_BUS,
            I2cAddress=0x60,
            DacType=I2cDacType.Mcp4728,
            Channels=4,
        ),
    ],
)
