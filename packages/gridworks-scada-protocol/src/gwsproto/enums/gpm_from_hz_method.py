from enum import auto

from gw.enums import GwStrEnum


class GpmFromHzMethod(GwStrEnum):
    """

    Values:
      - Constant

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#gpmfromhzmethod)
    """

    Constant = auto()

    @classmethod
    def default(cls) -> "GpmFromHzMethod":
        return cls.Constant

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gpm.from.hz.method"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
