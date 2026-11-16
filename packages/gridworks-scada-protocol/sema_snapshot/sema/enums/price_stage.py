from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class PriceStage(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/price.stage/000"""

    Provisional = auto()
    Final = auto()

    @classmethod
    def default(cls) -> "PriceStage":
        return cls.Provisional

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "price.stage"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
