from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class FloRefusalReason(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/flo.refusal.reason/000"""

    Unknown = auto()
    NoTuning = auto()
    NoMatrix = auto()
    BuildFailed = auto()
    BuildLost = auto()
    PastDeadline = auto()

    @classmethod
    def default(cls) -> "FloRefusalReason":
        return cls.Unknown

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "flo.refusal.reason"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
