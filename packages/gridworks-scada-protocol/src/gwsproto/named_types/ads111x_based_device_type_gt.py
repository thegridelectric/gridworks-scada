from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, PositiveInt, StrictInt

from gwsproto.enums import TelemetryName


class Ads111xBasedDeviceTypeGt(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/ads111x.based.device.type.gt/000
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
