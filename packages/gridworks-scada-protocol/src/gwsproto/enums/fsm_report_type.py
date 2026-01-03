from enum import auto

from gw.enums import GwStrEnum


class FsmReportType(GwStrEnum):
    """

    Values:
      - Other
      - Event
      - Action

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#fsmreporttype)
      - [More Info](https://gridworks-protocol.readthedocs.io/en/latest/finite-state-machines.html)
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
