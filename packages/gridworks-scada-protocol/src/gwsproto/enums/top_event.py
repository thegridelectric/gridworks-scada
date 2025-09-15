from enum import auto
from typing import List

from gw.enums import GwStrEnum


class TopEvent(GwStrEnum):
    """
    
    Values:
      - AdminWakesUp
      - AdminTimesOut

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#topevent)
    """

    AdminWakesUp = auto()
    AdminTimesOut = auto()

    @classmethod
    def default(cls) -> "TopEvent":
        return cls.AdminWakesUp

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "top.event"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
