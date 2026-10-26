from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class RefrigerantCycle(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw.refrigerant.cycle/000
    """

    Single = auto()
    Cascade = auto()

    @classmethod
    def default(cls) -> "RefrigerantCycle":
        return cls.Single

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.refrigerant.cycle"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
