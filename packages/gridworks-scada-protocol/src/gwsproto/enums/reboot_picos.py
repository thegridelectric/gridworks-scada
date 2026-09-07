# Versioned Enum:
#  - additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class RebootPicos(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/reboot.picos/000"""

    RebootPicos = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "RebootPicos":
        return cls.RebootPicos

    @classmethod
    def enum_name(cls) -> str:
        return "reboot.picos"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
