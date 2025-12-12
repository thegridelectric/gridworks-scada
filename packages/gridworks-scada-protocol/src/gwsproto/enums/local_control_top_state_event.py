from enum import auto
from gw.enums import GwStrEnum

class LocalControlTopStateEvent(GwStrEnum):
    SystemCold = auto()
    TopGoDormant = auto()
    TopWakeUp = auto()
    JustOffpeak = auto()
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
        return "local.control.top.state.event.neb" # non-electric backup

    @classmethod
    def enum_version(cls) -> str:
        return "000"