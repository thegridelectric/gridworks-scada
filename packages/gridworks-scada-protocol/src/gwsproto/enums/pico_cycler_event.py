from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class PicoCyclerEvent(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/pico.cycler.event/000
    """

    WakeUp = auto()
    GoDormant = auto()
    PicoMissing = auto()
    ConfirmOpened = auto()
    StartClosing = auto()
    ConfirmClosed = auto()
    ConfirmRebooted = auto()
    ShakeZombies = auto()
    RebootDud = auto()

    @classmethod
    def default(cls) -> "PicoCyclerEvent":
        return cls.ConfirmRebooted

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "pico.cycler.event"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
