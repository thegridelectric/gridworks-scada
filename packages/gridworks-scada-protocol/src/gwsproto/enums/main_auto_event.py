from enum import auto
from typing import List

from gw.enums import GwStrEnum


class MainAutoEvent(GwStrEnum):
    """
    
    Values:
      - DispatchContractLive # HomeAlone -> Atn
      - ContractGracePeriodEnds # Atn -> HomeAlone
      - AtnReleasesControl # Atn -> HomeAlone
      - AllyGivesUp # Atn -> HomeAlone
      - AutoGoesDormant # Atn or HomeAlone -> Dormant
      - AutoWakesUp # Dormant -> HomeAlone

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#mainautoevent)
    """

    DispatchContractLive = auto()
    ContractGracePeriodEnds = auto()
    AtnReleasesControl = auto()
    AllyGivesUp = auto()
    AutoGoesDormant = auto()
    AutoWakesUp = auto()

    @classmethod
    def default(cls) -> "MainAutoEvent":
        return cls.AutoWakesUp

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "main.auto.event"

    @classmethod
    def enum_version(cls) -> str:
        return "001"
