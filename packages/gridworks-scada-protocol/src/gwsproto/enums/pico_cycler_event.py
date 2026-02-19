from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class PicoCyclerEvent(AslEnum):
    """
    
    Values:
      - WakeUp
      - GoDormant
      - PicoMissing
      - ConfirmOpened
      - StartClosing
      - ConfirmClosed
      - ConfirmRebooted
      - ShakeZombies
      - RebootDud

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#picocyclerevent)
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
