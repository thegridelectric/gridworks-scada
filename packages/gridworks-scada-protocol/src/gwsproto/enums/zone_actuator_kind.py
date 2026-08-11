from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ZoneActuatorKind(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/zone.actuator.kind/000"""

    FloorLoop = auto()
    Fancoil = auto()

    @classmethod
    def default(cls) -> "ZoneActuatorKind":
        return cls.FloorLoop

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "zone.actuator.kind"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
