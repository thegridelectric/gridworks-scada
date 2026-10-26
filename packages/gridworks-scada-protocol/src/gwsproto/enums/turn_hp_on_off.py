from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class TurnHpOnOff(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/turn.hp.on.off/000
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
