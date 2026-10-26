from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class LocalControlBufferOnlyState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw1.local.control.buffer.only.state/001"""

    Initializing = auto()
    HpOn = auto()
    HpOff = auto()
    Dormant = auto()

    @classmethod
    def default(cls) -> "LocalControlBufferOnlyState":
        return cls.Initializing

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.local.control.buffer.only.state"

    @classmethod
    def enum_version(cls) -> str:
        return "001"
