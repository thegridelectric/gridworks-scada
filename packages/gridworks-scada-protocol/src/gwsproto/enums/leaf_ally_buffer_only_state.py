from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class LeafAllyBufferOnlyState(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.leaf.ally.buffer.only.state/000"""

    Dormant = auto()
    Initializing = auto()
    HpOn = auto()
    HpOff = auto()
    HpOffNonElectricBackup = auto()

    @classmethod
    def default(cls) -> "LeafAllyBufferOnlyState":
        return cls.Dormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.leaf.ally.buffer.only.state"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"
