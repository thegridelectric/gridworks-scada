from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonEmptyString
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveFloat
from sema_snapshot.sema.property_format import PositiveInt


class HpDeviceTypeGt(SemaType):
    """Sema: https://schemas.electricity.works/types/hp.device.type.gt/000"""

    device_type: PascalCase
    display_name: str | None = None
    max_kw_el: PositiveFloat
    heating_capacity_btu_hr: PositiveInt
    cooling_capacity_btu_hr: PositiveInt
    primary_pump_factory_installed: bool
    primary_pump_overridable: bool
    primary_pump_always_on: bool
    refrigerant: NonEmptyString | None = None
    compressor_rated_amps: PositiveFloat | None = None
    mca: PositiveFloat | None = None
    mop: PositiveFloat | None = None
    product_info_url: str | None = None
    type_name: Literal["hp.device.type.gt"] = "hp.device.type.gt"
    version: Literal["000"] = "000"
