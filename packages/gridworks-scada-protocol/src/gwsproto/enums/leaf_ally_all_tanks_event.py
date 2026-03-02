from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class LeafAllyAllTanksEvent(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.leaf.ally.all.tanks.event/000"""

    GoDormant = auto()
    WakeUp = auto()
    NoMoreElec = auto()
    ElecBufferFull = auto()
    ElecBufferEmpty = auto()
    NoElecBufferFull = auto()
    NoElecBufferEmpty = auto()
    StartNonElectricBackup = auto()
    StopNonElectricBackup = auto()
    DefrostDetected = auto()

    @classmethod
    def default(cls) -> "LeafAllyAllTanksEvent":
        return cls.GoDormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.leaf.ally.all.tanks.event"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"