from enum import auto
from typing import List

from gw.enums import GwStrEnum


class HomeAloneStrategy(GwStrEnum):
    """
    Values:
      - Winter
      - Shoulder

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#homealonetopstate)
    """
    Winter = auto()
    Shoulder = auto()


    @classmethod
    def default(cls) -> "HomeAloneStrategy":
        return cls.Winter

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "home.alone.strategy"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
