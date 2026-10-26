from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import TelemetryName
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt


class ElectricMeterDeviceTypeGt(SemaType):
    """Sema: https://schemas.electricity.works/types/electric.meter.device.type.gt/000"""

    device_type: PascalCase
    display_name: str | None = None
    min_poll_period_ms: PositiveInt | None = None
    telemetry_name_list: list[TelemetryName]
    default_baud: StrictInt | None = None
    type_name: Literal["electric.meter.device.type.gt"] = (
        "electric.meter.device.type.gt"
    )
    version: Literal["000"] = "000"
