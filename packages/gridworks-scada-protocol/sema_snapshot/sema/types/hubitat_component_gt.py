from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.hubitat_gt import HubitatGt


class HubitatComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/hubitat.component.gt/000"""

    component_id: UUID4Str
    device_type: PascalCase
    hubitat: HubitatGt
    display_name: str | None = None
    hw_uid: str | None = None
    type_name: Literal["hubitat.component.gt"] = "hubitat.component.gt"
    version: Literal["000"] = "000"
