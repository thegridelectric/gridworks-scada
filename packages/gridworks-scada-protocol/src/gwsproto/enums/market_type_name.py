from enum import auto
from typing import List
from gwsproto.enums.gw_str_enum import AslEnum


class MarketTypeName(AslEnum):
    """
    Categorizes different markets run by MarketMaker

    ASL: https://schemas.electricity.works/enums/market.type.name/000
    """

    unknown = auto()
    rt5gate5 = auto()
    rt60gate5 = auto()
    da60 = auto()
    rt60gate30 = auto()
    rt15gate5 = auto()
    rt30gate5 = auto()
    rt60gate30b = auto()

    @classmethod
    def default(cls) -> "MarketTypeName":
        return cls.unknown

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "market.type.name"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
