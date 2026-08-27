from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class HzCalcMethod(AslEnum):
    """Sema: https://schemas.electricity.works/enums/hz.calc.method/001"""

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
