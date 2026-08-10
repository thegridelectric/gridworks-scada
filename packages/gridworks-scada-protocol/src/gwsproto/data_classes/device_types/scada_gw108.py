from gwsproto.enums import (
    DeviceType,
    I2cAdcType,
    I2cDacType,
    I2cMuxType,
    RelayWiringConfig,
    TelemetryName,
)
from gwsproto.named_types.i2c_ct_interface_capability import I2cCtInterfaceCapability
from gwsproto.named_types.i2c_bus import I2cBus
from gwsproto.named_types.i2c_dac_capability import I2cDacCapability
from gwsproto.named_types.i2c_expander import I2cExpander
from gwsproto.named_types.i2c_mux import I2cMux
from gwsproto.named_types.i2c_relay_capability import I2cRelayCapability
from gwsproto.named_types.i2c_thermistor_interface_capability import (
    I2cThermistorInterfaceCapability,
)
from gwsproto.named_types.native_gpio_pin import NativeGpioPin
from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt

# All gw108 I²C peripherals (GPIO expanders 0x20/0x21, ADCs 0x48/0x49, the
# TCA9548A mux 0x70 and the three MCP4728 DACs behind it, all at 0x60) share
# one bus -> /dev/i2c-1. The two expanders are soldered at fixed addresses:
# expander 1 = 0x20, expander 2 = 0x21. The DACs share an address, which is
# why they sit behind the mux: Dac1 (mux channel 1) drives zones 1-3 on its
# channels A-C, Dac2 (channel 2) zones 4-6, Dac3 (channel 3) the plant
# pumps (A=primary, B=store, C=secondary).
DEFAULT_BUS = "DefaultBus"


def _relay(
    expander_idx: int,
    register: int,
    bit: int,
    *wiring: RelayWiringConfig,
    name: str,
    notes: str | None = None,
) -> I2cRelayCapability:
    return I2cRelayCapability(
        RelayName=name,
        ExpanderIdx=expander_idx,
        RegisterIndex=register,
        BitIndex=bit,
        SupportedWiringConfigs=list(wiring),
        Notes=notes,
    )


gw108_device_type = ScadaDeviceTypeGt(
    DeviceType=DeviceType.GridworksScadaGw108.value,
    DisplayName="GridWorks SCADA Gw108",
    TelemetryNameList=[TelemetryName.RelayState],  # FIX: CT / thermistor telemetry names still to settle
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
    Expanders=[
        I2cExpander(ExpanderIdx=1, I2cBus=DEFAULT_BUS, I2cAddress=0x20),
        I2cExpander(ExpanderIdx=2, I2cBus=DEFAULT_BUS, I2cAddress=0x21),
    ],
    I2cRelays=[
        _relay(1, 2, 0, RelayWiringConfig.DoubleThrow, name="Zone1Failsafe"),
        _relay(1, 2, 1, RelayWiringConfig.DoubleThrow, name="Zone2Failsafe"),
        _relay(1, 2, 2, RelayWiringConfig.DoubleThrow, name="Zone3Failsafe"),
        _relay(1, 2, 3, RelayWiringConfig.DoubleThrow, name="Zone4Failsafe"),
        _relay(1, 2, 4, RelayWiringConfig.DoubleThrow, name="Zone5Failsafe"),
        _relay(1, 2, 5, RelayWiringConfig.DoubleThrow, name="Zone6Failsafe"),
        _relay(1, 3, 0, RelayWiringConfig.NormallyOpen, name="Zone1Scada"),
        _relay(1, 3, 1, RelayWiringConfig.NormallyOpen, name="Zone2Scada"),
        _relay(1, 3, 2, RelayWiringConfig.NormallyOpen, name="Zone3Scada"),
        _relay(1, 3, 3, RelayWiringConfig.NormallyOpen, name="Zone4Scada"),
        _relay(1, 3, 4, RelayWiringConfig.NormallyOpen, name="Zone5Scada"),
        _relay(1, 3, 5, RelayWiringConfig.NormallyOpen, name="Zone6Scada"),
        _relay(
            2,
            2,
            1,
            RelayWiringConfig.NormallyOpen,
            name="BufferTop",
            notes="Upper buffer resistive heating element",
        ),
        _relay(
            2,
            2,
            2,
            RelayWiringConfig.NormallyOpen,
            name="BufferBottom",
            notes="Lower buffer resistive heating element",
        ),
        _relay(
            2,
            3,
            6,
            RelayWiringConfig.NormallyOpen,
            name="StoreTop",
            notes="Upper buffer resistive heating element",
        ),
        _relay(
            2,
            3,
            7,
            RelayWiringConfig.NormallyOpen,
            name="StoreBottom",
            notes="Lower buffer resistive heating element",
        ),
        _relay(
            2,
            2,
            0,
            RelayWiringConfig.NormallyOpen,
            name="HeatPumpEnable",
            notes="??",
        ),
        _relay(
            2,
            2,
            3,
            RelayWiringConfig.DoubleThrow,
            name="BoilerBufferValve",
            notes="??",
        ),
        _relay(
            2,
            2,
            4,
            RelayWiringConfig.NormallyClosed,
            name="BoilerIntercept",
            notes="By default, signal goes to boiler. ",
        ),
        _relay(2, 2, 7, RelayWiringConfig.NormallyOpen, name="PrimaryPump"),
        _relay(2, 3, 5, RelayWiringConfig.NormallyOpen, name="SecondaryPump"),
        _relay(2, 3, 4, RelayWiringConfig.NormallyOpen, name="StorePump"),
        _relay(2, 3, 3, RelayWiringConfig.DoubleThrow, name="DischargeValve"),
        _relay(2, 3, 2, RelayWiringConfig.DoubleThrow, name="IsoValve"),
        _relay(2, 3, 1, RelayWiringConfig.DoubleThrow, name="IsoValveFailsafe"),
        _relay(
            2,
            3,
            0,
            RelayWiringConfig.NormallyOpen,
            RelayWiringConfig.NormallyClosed,
            RelayWiringConfig.DoubleThrow,
            name="FcmMisc",
        ),
        _relay(
            2,
            2,
            5,
            RelayWiringConfig.NormallyOpen,
            RelayWiringConfig.NormallyClosed,
            RelayWiringConfig.DoubleThrow,
            name="Misc1",
        ),
        _relay(
            2,
            2,
            6,
            RelayWiringConfig.NormallyOpen,
            RelayWiringConfig.NormallyClosed,
            RelayWiringConfig.DoubleThrow,
            name="Misc2",
        ),
    ],
    CtAdc=I2cCtInterfaceCapability(
        Name="Ct",
        I2cBus=DEFAULT_BUS,
        I2cAddress=0x48,
        AdcType=I2cAdcType.Ads1115,
        AdcReferenceVolts=3.3,
        Channels=4,
    ),
    ThermistorAdcs=[
        I2cThermistorInterfaceCapability(
            Name="Thermistors",
            I2cBus=DEFAULT_BUS,
            I2cAddress=0x49,
            AdcType=I2cAdcType.Ads1115,
            SupportedDataRatesSps=[8, 16, 32, 64, 128, 250, 475, 860],
            # Divider pull-up supply (the old PullupResistorKOhms=5.65 is now
            # SeriesResistanceKOhms).
            AdcReferenceVolts=3.3,
            SeriesResistanceKOhms=5.65,
        )
    ],
    Muxes=[
        I2cMux(
            MuxName="DacMux",
            I2cBus=DEFAULT_BUS,
            I2cAddress=0x70,
            MuxType=I2cMuxType.Tca9548a,
            Channels=8,
        ),
    ],
    Dacs=[
        I2cDacCapability(
            DacName="Dac1",
            I2cBus=DEFAULT_BUS,
            I2cAddress=0x60,
            MuxName="DacMux",
            MuxChannel=1,
            DacType=I2cDacType.Mcp4728,
            Channels=4,
        ),
        I2cDacCapability(
            DacName="Dac2",
            I2cBus=DEFAULT_BUS,
            I2cAddress=0x60,
            MuxName="DacMux",
            MuxChannel=2,
            DacType=I2cDacType.Mcp4728,
            Channels=4,
        ),
        I2cDacCapability(
            DacName="Dac3",
            I2cBus=DEFAULT_BUS,
            I2cAddress=0x60,
            MuxName="DacMux",
            MuxChannel=3,
            DacType=I2cDacType.Mcp4728,
            Channels=4,
        ),
    ],
)
