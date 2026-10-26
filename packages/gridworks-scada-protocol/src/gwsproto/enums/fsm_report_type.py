from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class FsmReportType(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/fsm.report.type/000
    """

    Other = auto()
    Event = auto()
    Action = auto()

    @classmethod
    def default(cls) -> "FsmReportType":
        return cls.Other

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "fsm.report.type"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
