from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class SetpointPhase(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/setpoint.phase/000"""

    Unknown = auto()
    LastHeatCallEndTemp = auto()
    SuspectZoneBelowSetpoint = auto()
    SuspectZoneAboveSetpoint = auto()

    @classmethod
    def default(cls) -> "SetpointPhase":
        return cls.Unknown

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "setpoint.phase"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
