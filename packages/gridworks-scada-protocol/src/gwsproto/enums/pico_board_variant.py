# Versioned Enum:
#  - additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class PicoBoardVariant(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/pico.board.variant/000"""

    Unknown = auto()
    PicoWiznetEth2040 = auto()
    PicoWiznetEth2350 = auto()
    PicoRaspberryWifi2040 = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "PicoBoardVariant":
        return cls.Unknown

    @classmethod
    def enum_name(cls) -> str:
        return "pico.board.variant"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
