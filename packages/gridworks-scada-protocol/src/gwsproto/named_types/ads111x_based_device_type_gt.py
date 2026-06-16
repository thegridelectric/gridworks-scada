from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, PositiveInt, StrictInt

from gwsproto.enums import TelemetryName


class Ads111xBasedDeviceTypeGt(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/ads111x.based.device.type.gt/000

    The specialized device-type record for an ADS111x-based analog temperature sensor
    category (the per-family successor to ads111x.based.cac.gt). Carries the
    category-level data: I2C addresses, terminal-block count, telemetry names.
    Hand-ported from the gwta sema snapshot runtime.
    """

    DeviceType: str
    DisplayName: Optional[str] = None
    MinPollPeriodMs: Optional[PositiveInt] = None
    AdsI2cAddressList: list[StrictInt]
    TotalTerminalBlocks: StrictInt
    TelemetryNameList: list[TelemetryName]
    TypeName: Literal["ads111x.based.device.type.gt"] = "ads111x.based.device.type.gt"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")
