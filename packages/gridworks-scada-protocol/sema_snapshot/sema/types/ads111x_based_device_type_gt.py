from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import TelemetryName
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt


class Ads111xBasedDeviceTypeGt(SemaType):
    """Sema: https://schemas.electricity.works/types/ads111x.based.device.type.gt/000"""

    device_type: PascalCase
    display_name: str | None = None
    min_poll_period_ms: PositiveInt | None = None
    ads_i2c_address_list: list[StrictInt]
    total_terminal_blocks: StrictInt
    telemetry_name_list: list[TelemetryName]
    type_name: Literal["ads111x.based.device.type.gt"] = "ads111x.based.device.type.gt"
    version: Literal["000"] = "000"
