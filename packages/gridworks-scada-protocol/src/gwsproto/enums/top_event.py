from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class TopEvent(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/top.event/000
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
