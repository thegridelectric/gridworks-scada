# Versioned Enum:
#  - additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class SinglePicoState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/single.pico.state/000"""

    Alive = auto()
    Flatlined = auto()
    Zombie = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "SinglePicoState":
        return cls.Flatlined

    @classmethod
    def enum_name(cls) -> str:
        return "single.pico.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
