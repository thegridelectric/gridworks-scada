from enum import auto
from typing import List

from gw.enums import GwStrEnum


class LocalControlTopState(GwStrEnum):
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
        return "local.control.top.state.neb" # non-electric backup

    @classmethod
    def enum_version(cls) -> str:
        return "000"
