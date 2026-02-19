from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class LeafAllyAllTanksState(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.leaf.ally.all.tanks.state/000"""

    Dormant = auto()
    Initializing = auto()
    HpOnStoreOff = auto()
    HpOnStoreCharge = auto()
    HpOffStoreOff = auto()
    HpOffStoreDischarge = auto()
    HpOffNonElectricBackup = auto()

    @classmethod
    def default(cls) -> "LeafAllyAllTanksState":
        return cls.Dormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]
    
    @classmethod
    def enum_name(cls) -> str:
        return "gw1.leaf.ally.all.tanks.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
