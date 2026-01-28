from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class Unit(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.local.control.top.event/000"""

    Unknown = auto()
    Unitless = auto()
    W = auto()
    Celcius = auto()
    Fahrenheit = auto()
    Gpm = auto()
    WattHours = auto()
    AmpsRms = auto()
    VoltsRms = auto()
    Gallons = auto()
    ThermostatStateEnum = auto()

    @classmethod
    def default(cls) -> "Unit":
        return cls.Unknown

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "spaceheat.unit"

    @classmethod
    def enum_version(cls) -> str:
        return "001"
