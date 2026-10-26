from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class SiegValveState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/sieg.valve.state/000"""

    FullySend = auto()
    FullyKeep = auto()
    KeepingMore = auto()
    KeepingLess = auto()
    SteadyBlend = auto()

    @classmethod
    def default(cls) -> "SiegValveState":
        return cls.FullySend

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "sieg.valve.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
