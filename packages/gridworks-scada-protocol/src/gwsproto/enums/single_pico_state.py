from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class SinglePicoState(AslEnum):
    """Sema: https://schemas.electricity.works/enums/single.pico.state/000"""

    Alive = auto()
    Flatlined = auto()
    Zombie = auto()

    @classmethod
    def default(cls) -> "SinglePicoState":
        return cls.Flatlined

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "single.pico.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
