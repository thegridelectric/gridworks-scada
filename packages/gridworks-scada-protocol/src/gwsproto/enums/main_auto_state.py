from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class MainAutoState(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.main.auto.state/000"""

    LocalControl = auto()
    LeafTransactiveNode = auto()
    Dormant = auto()

    @classmethod
    def default(cls) -> "MainAutoState":
        return cls.LocalControl

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.main.auto.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
