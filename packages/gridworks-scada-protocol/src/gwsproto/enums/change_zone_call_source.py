from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ChangeZoneCallSource(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/change.zone.call.source/000"""

    SwitchToWallThermostat = auto()
    SwitchToScada = auto()

    @classmethod
    def default(cls) -> "ChangeZoneCallSource":
        return cls.SwitchToWallThermostat

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "change.zone.call.source"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
