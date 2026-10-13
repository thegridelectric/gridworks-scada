from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class LogLevel(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/log.level/000"""

    Critical = auto()
    Error = auto()
    Warning = auto()
    Info = auto()
    Debug = auto()
    Trace = auto()

    @classmethod
    def default(cls) -> "LogLevel":
        return cls.Info

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "log.level"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
