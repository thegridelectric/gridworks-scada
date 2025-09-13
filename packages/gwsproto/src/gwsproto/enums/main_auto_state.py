from enum import auto
from typing import List

from gw.enums import GwStrEnum


class MainAutoState(GwStrEnum):
    """
    
    Values:
      - HomeAlone
      - Atn
      - Dormant

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#mainautostate)
    """

    HomeAlone = auto()
    Atn = auto()
    Dormant = auto()

    @classmethod
    def default(cls) -> "MainAutoState":
        return cls.HomeAlone

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "main.auto.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
