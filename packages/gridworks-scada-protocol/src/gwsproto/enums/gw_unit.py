from enum import auto

from gw.enums import GwStrEnum


class GwUnit(GwStrEnum):
    Unknown = auto()
    Unitless = auto()
    FahrenheitX100 = auto()
    Watts = auto()
    WattHours = auto()
    VoltsX100 = auto()
    AmpsX100 = auto()
    Gallons = auto()
    GpmX100 = auto()

    @classmethod
    def default(cls) -> "GwUnit":
        return cls.Unknown

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]
    
    @classmethod
    def enum_name(cls) -> str:
        return "gw1.unit"

    @classmethod
    def enum_version(cls) -> str:
        return "000"