from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class MainAutoEvent(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.main.auto.event/000"""

    DispatchContractLive = auto()
    ContractGracePeriodEnds = auto()
    LtnReleasesControl = auto()
    AllyGivesUp = auto()
    AutoGoesDormant = auto()
    AutoWakesUp = auto()

    @classmethod
    def default(cls) -> "MainAutoEvent":
        return cls.AutoWakesUp

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.main.auto.event"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
