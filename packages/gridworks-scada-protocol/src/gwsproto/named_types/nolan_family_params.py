from typing import Literal

from gwsproto.enums import SeasonalStorageMode
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class NolanFamilyParams(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.nolan.family.params/000"""

    KeepBufferFull: bool
    SeasonalStorageMode: SeasonalStorageMode
    TypeName: Literal["gw.nolan.family.params"] = "gw.nolan.family.params"
    Version: Literal["000"] = "000"
