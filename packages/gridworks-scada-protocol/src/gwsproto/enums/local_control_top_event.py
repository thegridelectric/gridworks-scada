from enum import auto
from gwsproto.enums.gw_str_enum import AslEnum

class LocalControlTopEvent(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.local.control.top.event/000"""

    SystemCold = auto()
    TopGoDormant = auto()
    TopWakeUp = auto()
    MissingData = auto()
    DataAvailable = auto()
    MonitorOnly = auto()
    MonitorAndControl = auto()
    CriticalZonesAtSetpointOffpeak = auto()

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.local.control.top.event"

    @classmethod
    def enum_version(cls) -> str:
        return "000"