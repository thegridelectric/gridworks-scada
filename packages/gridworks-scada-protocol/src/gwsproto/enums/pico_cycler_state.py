from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class PicoCyclerState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/pico.cycler.state/000
    """

    Dormant = auto()
    PicosLive = auto()
    RelayOpening = auto()
    RelayOpen = auto()
    RelayClosing = auto()
    PicosRebooting = auto()
    AllZombies = auto()

    @classmethod
    def default(cls) -> "PicoCyclerState":
        return cls.PicosLive

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "pico.cycler.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
