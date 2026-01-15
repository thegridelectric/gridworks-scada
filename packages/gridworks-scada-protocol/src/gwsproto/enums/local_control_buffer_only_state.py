
from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class LocalControlBufferOnlyState(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.local.control.buffer.only.state/000"""

    Initializing = auto()
    HpOn = auto()
    HpOff = auto()
    Dormant = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.local.control.buffer.only.state"

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]


    @classmethod
    def default(cls) -> "LocalControlBufferOnlyState":
        return cls.Initializing


    @classmethod
    def version(cls) -> str:
        return "000"