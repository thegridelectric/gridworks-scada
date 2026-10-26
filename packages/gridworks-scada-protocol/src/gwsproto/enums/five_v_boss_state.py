from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class FiveVBossState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/five.v.boss.state/000"""

    PicoCycler = auto()
    TurningOff = auto()
    FiveVOff = auto()
    TurningOn = auto()

    @classmethod
    def default(cls) -> "FiveVBossState":
        return cls.PicoCycler

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "five.v.boss.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
