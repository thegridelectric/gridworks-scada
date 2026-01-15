from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class TurnHpOnOff(AslEnum):
    """
    
    Values:
      - TurnOn
      - TurnOff

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#turnhponoff)
    """

    TurnOn = auto()
    TurnOff = auto()

    @classmethod
    def default(cls) -> "TurnHpOnOff":
        return cls.TurnOn

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "turn.hp.on.off"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
