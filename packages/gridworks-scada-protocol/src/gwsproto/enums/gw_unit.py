from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class GwUnit(AslEnum):
    """Encoding used for Derived channels"""
    Unknown = auto()
    Unitless = auto()
    FahrenheitX100 = auto()
    Watts = auto()
    WattHours = auto()
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