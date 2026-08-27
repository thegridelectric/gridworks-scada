from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class GpmFromHzMethod(AslEnum):
    """Sema: https://schemas.electricity.works/enums/gpm.from.hz.method/000"""

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
