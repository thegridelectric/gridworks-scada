# Versioned Enum:
#  - additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ScadaCmdRefusalReason(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw.scada.cmd.refusal.reason/000"""

    Unknown = auto()
    Busy = auto()
    NotMyBoss = auto()
    UnknownEvent = auto()
    OutOfRange = auto()
    NotAControlNode = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "ScadaCmdRefusalReason":
        return cls.Unknown

    @classmethod
    def enum_name(cls) -> str:
        return "gw.scada.cmd.refusal.reason"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
