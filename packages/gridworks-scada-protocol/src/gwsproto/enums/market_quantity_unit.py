from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class MarketQuantityUnit(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/market.quantity.unit/000
    """

    AvgMW = auto()
    AvgkW = auto()

    @classmethod
    def default(cls) -> "MarketQuantityUnit":
        return cls.AvgMW

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "market.quantity.unit"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
