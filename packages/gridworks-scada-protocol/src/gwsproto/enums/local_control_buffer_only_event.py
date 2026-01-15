
from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class LocalControlBufferOnlyEvent(AslEnum):
    """ ASL: https://schemas.electricity.works/enums/gw1.local.control.buffer.only.event/000"""
    WakeUp = auto()
    OnPeakStart = auto()
    BufferFull = auto()
    BufferNeedsCharge = auto()
    TemperaturesAvailable = auto()
    GoDormant = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.local.control.buffer.only.event"

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "LocalControlBufferOnlyEvent":
        return cls.WakeUp

    @classmethod
    def version(cls) -> str:
        return "000"