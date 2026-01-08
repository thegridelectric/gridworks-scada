from typing import Literal

from gwsproto.enums import TelemetryName
from gwsproto.named_types import ComponentAttributeClassGt


class ElectricMeterCacGt(ComponentAttributeClassGt):
    TelemetryNameList: list[TelemetryName]
    DefaultBaud: int | None = None
    TypeName: Literal["electric.meter.cac.gt"] = "electric.meter.cac.gt"
    Version: Literal["001"] = "001"
