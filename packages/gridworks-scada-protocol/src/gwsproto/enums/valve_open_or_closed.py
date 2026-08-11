from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ValveOpenOrClosed(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/valve.open.or.closed/000"""

    ValveOpen = auto()
    ValveClosed = auto()

    @classmethod
    def default(cls) -> "ValveOpenOrClosed":
        return cls.ValveOpen

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "valve.open.or.closed"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
