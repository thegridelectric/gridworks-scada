from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import SeasonalStorageMode
from sema_snapshot.sema.enums import SiegLoopStrategy


class House0FamilyParams(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.house0.family.params/000"""

    sieg_loop_strategy: SiegLoopStrategy
    keep_buffer_full: bool
    seasonal_storage_mode: SeasonalStorageMode
    type_name: Literal["gw.house0.family.params"] = "gw.house0.family.params"
    version: Literal["000"] = "000"
