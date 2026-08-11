from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ChangeValveState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/change.valve.state/000"""

    OpenValve = auto()
    CloseValve = auto()

    @classmethod
    def default(cls) -> "ChangeValveState":
        return cls.OpenValve

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "change.valve.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
