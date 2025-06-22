from enum import auto
from typing import List

from gw.enums import GwStrEnum


class AtomicAllyState(GwStrEnum):
    Dormant = auto()
    Initializing = auto()
    HpOnStoreOff = auto()
    HpOnStoreCharge = auto()
    HpOffStoreOff = auto()
    HpOffStoreDischarge = auto()
    HpOffOilBoilerTankAquastat = auto()

    @classmethod
    def default(cls) -> "AtomicAllyState":
        return cls.Dormant

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]
    
    @classmethod
    def enum_name(cls) -> str:
        return "atomic.ally.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
