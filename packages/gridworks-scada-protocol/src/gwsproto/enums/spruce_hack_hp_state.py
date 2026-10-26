from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class SpruceHackHpState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/spruce.hack.hp.state/000"""

    Unknown = auto()
    HpDetectedOn = auto()
    HpDetectedOff = auto()

    @classmethod
    def default(cls) -> "SpruceHackHpState":
        return cls.Unknown

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "spruce.hack.hp.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
