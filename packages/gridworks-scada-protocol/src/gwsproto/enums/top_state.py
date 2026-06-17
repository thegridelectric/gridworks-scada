from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class TopState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/top.state/000
    """

    Auto = auto()
    Admin = auto()

    @classmethod
    def default(cls) -> "TopState":
        return cls.Auto

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "top.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
