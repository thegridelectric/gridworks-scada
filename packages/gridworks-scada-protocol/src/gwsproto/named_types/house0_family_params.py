from typing import Literal

from gwsproto.enums import SeasonalStorageMode, SiegLoopStrategy
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class House0FamilyParams(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.house0.family.params/000"""

    SiegLoopStrategy: SiegLoopStrategy
    KeepBufferFull: bool
    SeasonalStorageMode: SeasonalStorageMode
    TypeName: Literal["gw.house0.family.params"] = "gw.house0.family.params"
    Version: Literal["000"] = "000"
