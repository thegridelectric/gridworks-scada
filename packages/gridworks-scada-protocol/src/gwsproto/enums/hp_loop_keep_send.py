# Literal Enum:
#  - no additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class HpLoopKeepSend(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/hp.loop.keep.send/000"""

    SendLess = auto()
    SendMore = auto()

    @classmethod
    def values(cls) -> List[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "HpLoopKeepSend":
        return cls.SendMore

    @classmethod
    def enum_name(cls) -> str:
        return "hp.loop.keep.send"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
