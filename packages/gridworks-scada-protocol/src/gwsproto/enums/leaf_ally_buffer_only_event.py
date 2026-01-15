from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum

class LeafAllyBufferOnlyEvent(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.leaf.ally.buffer.only.event/000"""

    GoDormant = auto()
    WakeUp = auto()
    NoMoreElec = auto()
    BufferFull = auto()
    ChargeBuffer = auto()
    StartNonElectricBackup = auto()
    StopNonElectricBackup = auto()

    @classmethod
    def default(cls) -> "LeafAllyBufferOnlyEvent":
        return cls.GoDormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.leaf.ally.buffer.only.event"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"

    
