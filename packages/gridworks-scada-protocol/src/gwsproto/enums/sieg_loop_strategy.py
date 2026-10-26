from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class SiegLoopStrategy(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/sieg.loop.strategy/000"""

    HoldFullSend = auto()
    StratProtect = auto()
    LwtControl = auto()

    @classmethod
    def default(cls) -> "SiegLoopStrategy":
        return cls.HoldFullSend

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "sieg.loop.strategy"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
