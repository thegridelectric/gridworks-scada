from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt, StrictInt

from gwsproto.enums import TelemetryName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ElectricMeterDeviceTypeGt(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/electric.meter.device.type.gt/000
    """

    DeviceType: str
    DisplayName: Optional[str] = None
    MinPollPeriodMs: Optional[PositiveInt] = None
    TelemetryNameList: list[TelemetryName]
    DefaultBaud: Optional[StrictInt] = None
    TypeName: Literal["electric.meter.device.type.gt"] = "electric.meter.device.type.gt"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")
