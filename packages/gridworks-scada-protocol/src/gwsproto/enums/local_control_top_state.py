from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class LocalControlTopState(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.lc.top.state/000"""

    Dormant = auto()
    UsingNonElectricBackup = auto()
    Normal = auto()
    ScadaBlind = auto()
    Monitor = auto()

    @classmethod
    def default(cls) -> "LocalControlTopState":
        return cls.Dormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.lc.top.state" # non-electric backup

    @classmethod
    def enum_version(cls) -> str:
        return "000"
