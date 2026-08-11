from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ZoneCallSource(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/zone.call.source/000"""

    WallThermostat = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "ZoneCallSource":
        return cls.WallThermostat

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "zone.call.source"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
