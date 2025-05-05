# Literal Enum:
#  - no additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto
from typing import List

from gw.enums import GwStrEnum


class ChangeKeepSend(GwStrEnum):
    """
    HpLoop relay - change to send more or send less
    """

    ChangeToKeepLess = auto()
    ChangeToKeepMore = auto()

    @classmethod
    def values(cls) -> List[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "ChangeKeepSend":
        return cls.ChangeToKeepLess

    @classmethod
    def enum_name(cls) -> str:
        return "change.keep.send"
