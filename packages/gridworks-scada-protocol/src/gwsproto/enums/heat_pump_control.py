from enum import auto

from gw.enums import GwStrEnum


class HeatPumpControl(GwStrEnum):
    """

    Values:
      - BufferTankAquastat
      - Scada

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#heatpumpcontrol)
    """

    BufferTankAquastat = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "HeatPumpControl":
        return cls.BufferTankAquastat

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "heat.pump.control"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
