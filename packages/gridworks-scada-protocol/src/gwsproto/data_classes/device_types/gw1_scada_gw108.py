from gwsproto.enums import MakeModel, RelayWiringConfig
from gwsproto.named_types.scada_device_type_gt import (
    ScadaDeviceTypeGt, 
    I2cBitAddress,
    I2cRelayConfig, 
    I2cAdcConfig,
    I2cThermistorInterfaceConfig,
    NativeGpioConfig,
    I2cDacConfig
)
from gwsproto.type_helpers.cacs_by_make_model import CACS_BY_MAKE_MODEL

gw108_device_type = ScadaDeviceTypeGt(
    MakeModel=MakeModel.GRIDWORKS__SCADA_GW108,
    ComponentAttributeClassId=CACS_BY_MAKE_MODEL[MakeModel.GRIDWORKS__SCADA_GW108],
    NativeGpio=NativeGpioConfig(
        Inputs={
            "Zone1Whitewire": 17,
            "Zone2Whitewire": 27,
            "Zone3Whitewire": 22,
            "Zone4Whitewire": 10,
            "Zone5Whitewire": 9,
            "Zone6Whitewire": 11,
            "Shutdown": 18,
        },
        Outputs={
            "TstatPower": 4,
            "Vdc": 23,
            "Watchdog": 24,
            "PowerOff": 25,
        },
    ),

    
    I2cRelays={
        "Zone1Failsafe": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=2, BitIndex=0),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
        ),
        "Zone2Failsafe": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=2, BitIndex=1),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
        ),
        "Zone3Failsafe": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=2, BitIndex=2),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
        ),
        "Zone4Failsafe": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=2, BitIndex=3),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
        ),
        "Zone5Failsafe": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=2, BitIndex=4),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
        ),
        "Zone6Failsafe": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=2, BitIndex=5),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
        ),
        "Zone1Scada": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=3, BitIndex=0),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
        ),
        "Zone2Scada": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=3, BitIndex=1),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
        ),
        "Zone3Scada": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=3, BitIndex=2),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
        ),
        "Zone4Scada": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=3, BitIndex=3),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
        ),
        "Zone5Scada": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=3, BitIndex=4),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
        ),
        "Zone6Scada": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x20, Register=3, BitIndex=5),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
        ),

        "BufferTop": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=2, BitIndex=1),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
            Notes="Upper buffer resistive heating element"
        ),
        "BufferBottom": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=2, BitIndex=2),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
            Notes="Lower buffer resistive heating element"
        ),
        "StoreTop": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=3, BitIndex=6),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
            Notes="Upper buffer resistive heating element"
        ),
        "StoreBottom": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=3, BitIndex=7),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
            Notes="Lower buffer resistive heating element"
        ),
        "HeatPumpEnable": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=2, BitIndex=0),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
            Notes="??"
        ),
        "BoilerBufferValve": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=2, BitIndex=3),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
            Notes="??"
        ),
        "BoilerIntercept": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=2, BitIndex=4),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyClosed],
            Notes="By default, signal goes to boiler. "
        ),
        "PrimaryPump": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=2, BitIndex=7),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
            Notes=""
        ),
        "SecondaryPump": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=3, BitIndex=5),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
            Notes=""
        ),
        "StorePump": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=3, BitIndex=4),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen],
            Notes=""
        ),
        "DischargeValve": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=3, BitIndex=3),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow], # check this?
            Notes=""
        ),
        "IsoValve": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=3, BitIndex=2),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
            Notes=""
        ),
        "IsoValveFailsafe": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=3, BitIndex=1),
            SupportedWiringConfigs=[RelayWiringConfig.DoubleThrow],
            Notes=""
        ),
        "FcmMisc": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=3, BitIndex=0),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen, 
                                    RelayWiringConfig.NormallyClosed,
                                    RelayWiringConfig.DoubleThrow],
            Notes=""
        ),
        "Misc1": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=2, BitIndex=5),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen, 
                                    RelayWiringConfig.NormallyClosed,
                                    RelayWiringConfig.DoubleThrow],
            Notes=""
        ),
        "Misc2": I2cRelayConfig(
            Address=I2cBitAddress(I2cAddress=0x21, Register=2, BitIndex=6),
            SupportedWiringConfigs=[RelayWiringConfig.NormallyOpen, 
                                    RelayWiringConfig.NormallyClosed,
                                    RelayWiringConfig.DoubleThrow],
            Notes=""
        ),
    },

    CtAdc=I2cAdcConfig(
        I2cAddress=0x48,
        AdcType="ADS1115",
        Channels=4,
    ),

    ThermistorAdcs=[
        I2cThermistorInterfaceConfig(
            I2cAddress=0x49,
            AdcType="ADS1115",
            PullupResistorKOhms=5.65,
        )
    ],

    Dacs={
        "Zones": I2cDacConfig(I2cAddress=0x60, DacType="MCP4728", Channels=4),
    },
)
