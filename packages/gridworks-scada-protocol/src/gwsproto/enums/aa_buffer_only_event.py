from enum import auto
from typing import List

from gw.enums import GwStrEnum


class AaBufferOnlyEvent(GwStrEnum):
    NoMoreElec = auto()
    BufferFull = auto()
    ChargeBuffer = auto()
    StartHackOil = auto()
    StopHackOil = auto()
    GoDormant = auto()
    WakeUp = auto()

    @classmethod
    def default(cls) -> "AaBufferOnlyEvent":
        return cls.GoDormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "aa.buffer.only.event"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"

    
