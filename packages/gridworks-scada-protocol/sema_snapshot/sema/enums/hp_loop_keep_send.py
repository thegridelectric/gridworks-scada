from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class HpLoopKeepSend(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/hp.loop.keep.send/000"""

    SendLess = auto()
    SendMore = auto()

    @classmethod
    def default(cls) -> "HpLoopKeepSend":
        return cls.SendMore

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "hp.loop.keep.send"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
