from enum import auto
from typing import List

from gw.enums import GwStrEnum


class AtomicAllyEvent(GwStrEnum):
    NoMoreElec = auto()
    ElecBufferFull = auto()
    ElecBufferEmpty = auto()
    NoElecBufferFull = auto()
    NoElecBufferEmpty = auto()
    WakeUp = auto()
    GoDormant = auto()
    StartHackOil = auto()
    StopHackOil = auto()

    @classmethod
    def default(cls) -> "AtomicAllyEvent":
        return cls.GoDormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "atomic.ally.event"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"