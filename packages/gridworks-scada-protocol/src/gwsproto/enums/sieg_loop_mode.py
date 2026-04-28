from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class SiegLoopMode(AslEnum):
    PidControl = auto()
    Fallback = auto()

    @classmethod
    def default(cls) -> "SiegLoopMode":
        return cls.Fallback

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.sieg.loop.mode"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
