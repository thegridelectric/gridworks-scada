from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class LocalControlStandbyTopState(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.local.control.standby.top.state/000"""

    EverythingOff = auto()
    Dormant = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.local.control.standby.top.state"

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "LocalControlStandbyTopState":
        return cls.EverythingOff
    
    @classmethod
    def version(cls) -> str:
        return "000"