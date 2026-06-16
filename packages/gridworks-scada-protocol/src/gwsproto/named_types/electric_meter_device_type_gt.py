from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, PositiveInt, StrictInt

from gwsproto.enums import TelemetryName


class ElectricMeterDeviceTypeGt(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/electric.meter.device.type.gt/000

    The specialized device-type record for an electric-meter category (the per-family
    successor to electric.meter.cac.gt): the telemetry names it reports, its shortest
    poll period, and its default serial baud. Hand-ported from the gwta snapshot.
    """

    DeviceType: str
    DisplayName: Optional[str] = None
    MinPollPeriodMs: Optional[PositiveInt] = None
    TelemetryNameList: list[TelemetryName]
    DefaultBaud: Optional[StrictInt] = None
    TypeName: Literal["electric.meter.device.type.gt"] = "electric.meter.device.type.gt"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")
