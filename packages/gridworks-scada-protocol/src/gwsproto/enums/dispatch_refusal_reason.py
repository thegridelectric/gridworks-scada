from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class DispatchRefusalReason(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw.dispatch.refusal.reason/000"""

    NoTaDeed = auto()
    OperatorHold = auto()
    ServiceContractBroken = auto()
    ScadaBlind = auto()
    InAdmin = auto()

    @classmethod
    def default(cls) -> "DispatchRefusalReason":
        return cls.OperatorHold

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.dispatch.refusal.reason"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
