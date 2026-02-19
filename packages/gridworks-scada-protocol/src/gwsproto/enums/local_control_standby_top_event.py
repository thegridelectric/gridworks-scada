from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class LocalControlStandbyTopEvent(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.local.control.standby.top.event/000"""

    TopWakeUp = auto()
    TopGoDormant = auto()
    
    @classmethod
    def enum_name(cls) -> str:
        return "gw1.local.control.standby.top.event"

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "LocalControlStandbyTopEvent":
        return cls.TopWakeUp
    
    @classmethod
    def version(cls) -> str:
        return "000"