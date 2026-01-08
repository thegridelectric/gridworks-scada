from enum import auto

from gw.enums import GwStrEnum


class HeatcallSource(GwStrEnum):
    """
    Used for reflecting the state of a double-throw relay that can toggle between a failsafe
    for providing a 24V heat call to a zone controller (aka Wall Thermostat) and the SCADA providing
    that heat call
    Values:
      - WallThermostat
      - Scada

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#heatcallsource)
    """

    WallThermostat = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "HeatcallSource":
        return cls.WallThermostat

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "heatcall.source"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
