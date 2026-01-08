from enum import auto

from gw.enums import GwStrEnum


class AquastatControl(GwStrEnum):
    """

    Values:
      - Boiler
      - Scada

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#aquastatcontrolstate)
    """

    Boiler = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "AquastatControl":
        return cls.Boiler

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "aquastat.control.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
