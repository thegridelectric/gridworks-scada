from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class LocalControlAllTanksEvent(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.local.control.all.tanks.event/000"""

    WakeUp = auto()
    OnPeakStart = auto()
    OffPeakStart = auto()
    OnPeakBufferFull = auto()
    OffPeakBufferFullStorageNotReady = auto()
    OffPeakBufferFullStorageReady = auto()
    OffPeakBufferEmpty = auto()
    OnPeakBufferEmpty = auto()
    OffPeakStorageReady = auto()
    OffPeakStorageNotReady = auto()
    OnPeakStorageColderThanBuffer = auto()
    TemperaturesAvailable = auto()
    GoDormant = auto()

    @classmethod
    def default(cls) -> "LocalControlAllTanksEvent":
        return cls.WakeUp

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.local.control.all.tanks.event"
    
    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def version(cls) -> str:
        return "000"
    