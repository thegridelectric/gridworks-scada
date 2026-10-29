from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class CirculatorRole(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw.circulator.role/000
    """

    Unknown = auto()
    Dist = auto()
    Primary = auto()
    Store = auto()
    Secondary = auto()

    @classmethod
    def default(cls) -> "CirculatorRole":
        return cls.Unknown

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.circulator.role"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
