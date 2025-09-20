from enum import auto
from typing import List

from gw.enums import GwStrEnum


class MarketQuantityUnit(GwStrEnum):
    """
    Quantity unit assigned to MarketMaker MarketType
    Values:
      - AvgMW
      - AvgkW

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#marketquantityunit)
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
