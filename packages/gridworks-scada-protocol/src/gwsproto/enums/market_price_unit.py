from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class MarketPriceUnit(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/market.price.unit/000
    """

    USDPerMWh = auto()

    @classmethod
    def default(cls) -> "MarketPriceUnit":
        return cls.USDPerMWh

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "market.price.unit"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
