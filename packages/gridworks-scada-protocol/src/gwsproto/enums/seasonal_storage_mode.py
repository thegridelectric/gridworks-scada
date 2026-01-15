from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class SeasonalStorageMode(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.seasonal.stoarge.mode/000"""

    AllTanks = auto()
    BufferOnly = auto()

    @classmethod
    def default(cls) -> "SeasonalStorageMode":
        return cls.AllTanks

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.seasonal.storage.mode"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
