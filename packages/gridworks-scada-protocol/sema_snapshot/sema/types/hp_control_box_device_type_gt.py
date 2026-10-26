from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveFloat


class HpControlBoxDeviceTypeGt(SemaType):
    """Sema: https://schemas.electricity.works/types/hp.control.box.device.type.gt/000"""

    device_type: PascalCase
    display_name: str | None = None
    primary_pump_factory_installed: bool
    primary_pump_overridable: bool
    primary_pump_always_on: bool
    water_pump_rated_amps: PositiveFloat | None = None
    backup_heater_kw_list: list[PositiveFloat] | None = None
    mca: PositiveFloat | None = None
    mop: PositiveFloat | None = None
    product_info_url: str | None = None
    type_name: Literal["hp.control.box.device.type.gt"] = (
        "hp.control.box.device.type.gt"
    )
    version: Literal["000"] = "000"
