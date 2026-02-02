from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class EmissionMethod(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.emission.method/000"""

    OnTrigger = auto()
    Periodic = auto()
    AsyncAndPeriodic = auto()

    @classmethod
    def default(cls) -> "EmissionMethod":
        return cls.OnTrigger

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.emission.method"

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def version(cls) -> str:
        return "000"