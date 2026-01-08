from enum import auto

from gw.enums import GwStrEnum


class Unit(GwStrEnum):
    """
    Specifies the physical unit of sensed data reported by SCADA
    Values:
      - Unknown
      - Unitless
      - W
      - Celcius
      - Fahrenheit
      - Gpm
      - WattHours
      - AmpsRms
      - VoltsRms
      - Gallons
      - ThermostatStateEnum

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#spaceheatunit)
    """

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
