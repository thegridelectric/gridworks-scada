from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class PrimaryFlowSource(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw.primary.flow.source/000
    """

    Measured = auto()
    DerivedSiegSum = auto()

    @classmethod
    def default(cls) -> "PrimaryFlowSource":
        return cls.Measured

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.primary.flow.source"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
