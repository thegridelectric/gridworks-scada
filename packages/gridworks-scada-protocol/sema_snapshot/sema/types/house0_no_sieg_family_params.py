from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import SeasonalStorageMode


class House0NoSiegFamilyParams(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.house0.no.sieg.family.params/000"""

    keep_buffer_full: bool
    seasonal_storage_mode: SeasonalStorageMode
    type_name: Literal["gw.house0.no.sieg.family.params"] = (
        "gw.house0.no.sieg.family.params"
    )
    version: Literal["000"] = "000"
