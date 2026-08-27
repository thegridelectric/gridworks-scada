from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class TempCalcMethod(AslEnum):
    """Sema: https://schemas.electricity.works/enums/temp.calc.method/000"""

    SimpleBetaForPico = auto()
    SimpleBeta = auto()

    @classmethod
    def default(cls) -> "TempCalcMethod":
        return cls.SimpleBeta

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "temp.calc.method"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
