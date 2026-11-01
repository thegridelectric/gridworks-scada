from enum import auto
from typing import List
from gwsproto.enums.gw_str_enum import SemaEnum


class MarketProductName(SemaEnum):
    """
    Sema: https://schemas.electricity.works/enums/gw.market.product.name/000
    """

    unknown = auto()
    da60 = auto()
    rt60gate5 = auto()
    rt60gate30 = auto()
    rt60gate30b = auto()
    rt30gate5 = auto()
    rt15gate5 = auto()
    rt5gate5 = auto()

    @classmethod
    def default(cls) -> "MarketProductName":
        return cls.unknown

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.market.product.name"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
