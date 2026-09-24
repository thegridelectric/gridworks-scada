from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class PrimaryPumpOwner(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw.primary.pump.owner/000
    """

    HeatPump = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "PrimaryPumpOwner":
        return cls.HeatPump

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.primary.pump.owner"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
