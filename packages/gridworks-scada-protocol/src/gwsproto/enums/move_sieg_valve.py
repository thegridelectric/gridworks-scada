from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class MoveSiegValve(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/move.sieg.valve/000"""

    MoveToFullSend = auto()
    MoveToFullKeep = auto()

    @classmethod
    def default(cls) -> "MoveSiegValve":
        return cls.MoveToFullSend

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "move.sieg.valve"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
