from typing import Literal, Optional

from gwsproto.enums import TelemetryName
from pydantic import BaseModel, PositiveInt
from gwsproto.enums import RelayWiringConfig


class I2cBitAddress(BaseModel):
    I2cAddress: int
    Register: int
    BitIndex: int


class I2cRelayConfig(BaseModel):
    Address: I2cBitAddress
    SupportedWiringConfigs: list[RelayWiringConfig]
    Notes: str | None = None

class I2cAdcConfig(BaseModel):
    I2cAddress: int
    AdcType: Literal["ADS1115"]
    Channels: PositiveInt

class I2cThermistorInterfaceConfig(BaseModel):
    I2cAddress: int
    AdcType: Literal["ADS1115"]
    PullupResistorKOhms: float

class I2cDacConfig(BaseModel):
    I2cAddress: int
    DacType: Literal["MCP4728"]
    Channels: PositiveInt


class NativeGpioConfig(BaseModel):
    Inputs: dict[str, int]    # name → BCM pin
    Outputs: dict[str, int]   # name → BCM pin


class ScadaDeviceTypeGt(BaseModel):
    """
    GridWorks SCADA board device type
    """

    DeviceType: str
    DisplayName: Optional[str] = None
    MinPollPeriodMs: Optional[PositiveInt] = None
    TelemetryNameList: list[TelemetryName]

    # --- Native GPIO (BCM pins) ---
    NativeGpio: NativeGpioConfig | None = None

    # --- I2C GPIO expanders (named relays / outputs) ---
    I2cRelays: dict[str, I2cRelayConfig] = {}

    # --- ADCs ---
    CtAdc: Optional[I2cAdcConfig] = None
    ThermistorAdcs: list[I2cThermistorInterfaceConfig] = []

    # --- DACs ---
    Dacs: dict[str, I2cDacConfig] = {}

    TypeName: Literal["gw1.scada.device.type.gt"] = "gw1.scada.device.type.gt"
    Version: Literal["001"] = "001"
