from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class NolanLcBufferOnlyState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw1.nolan.lc.buffer.only.state/000"""

    Initializing = auto()
    HpCallOn = auto()
    HpCallOff = auto()
    Dormant = auto()

    @classmethod
    def default(cls) -> "NolanLcBufferOnlyState":
        return cls.Initializing

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.nolan.lc.buffer.only.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
