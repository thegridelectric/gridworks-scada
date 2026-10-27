from typing import Literal

from gwsproto.enums import SeasonalStorageMode
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class House0NoSiegFamilyParams(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.house0.no.sieg.family.params/000"""

    KeepBufferFull: bool
    SeasonalStorageMode: SeasonalStorageMode
    TypeName: Literal["gw.house0.no.sieg.family.params"] = "gw.house0.no.sieg.family.params"
    Version: Literal["000"] = "000"
