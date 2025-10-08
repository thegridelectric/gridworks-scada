from enum import auto
from typing import List

from gw.enums import GwStrEnum


class AaBufferOnlyState(GwStrEnum):
    Initializing = auto()
    HpOn = auto()
    HpOff = auto()
    HpOffOilBoilerTankAquastat = auto()
    Dormant = auto()

    @classmethod
    def defualt(cls) -> "AaBufferOnlyState":
        return cls.Dormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "aa.buffer.only.state"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"
