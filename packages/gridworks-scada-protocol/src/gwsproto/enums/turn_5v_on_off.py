from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class Turn5VOnOff(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/turn.5v.on.off/000"""

    TurnOn = auto()
    TurnOff = auto()

    @classmethod
    def default(cls) -> "Turn5VOnOff":
        return cls.TurnOn

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "turn.5v.on.off"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
