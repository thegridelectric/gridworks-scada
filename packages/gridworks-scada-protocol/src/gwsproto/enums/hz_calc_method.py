from enum import auto

from gw.enums import GwStrEnum


class HzCalcMethod(GwStrEnum):
    """

    Values:
      - BasicExpWeightedAvg
      - BasicButterWorth

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#hzcalcmethod)
    """

    BasicExpWeightedAvg = auto()
    BasicButterWorth = auto()
    UniformWindow = auto()

    @classmethod
    def default(cls) -> "HzCalcMethod":
        return cls.BasicExpWeightedAvg

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "hz.calc.method"

    @classmethod
    def enum_version(cls) -> str:
        return "001"
