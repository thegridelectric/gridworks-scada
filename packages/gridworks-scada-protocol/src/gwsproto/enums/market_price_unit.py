from enum import auto
from typing import List

from gw.enums import GwStrEnum


class MarketPriceUnit(GwStrEnum):
    """
    Price unit assigned to MarketMaker MarketType
    Values:
      - USDPerMWh

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#marketpriceunit)
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
