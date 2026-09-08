from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class PicoBoardVariant(AslEnum):
    """Sema: https://schemas.electricity.works/enums/pico.board.variant/000"""

    Unknown = auto()
    PicoWiznetEth2040 = auto()
    PicoWiznetEth2350 = auto()
    PicoRaspberryWifi2040 = auto()

    @classmethod
    def default(cls) -> "PicoBoardVariant":
        return cls.Unknown

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "pico.board.variant"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
