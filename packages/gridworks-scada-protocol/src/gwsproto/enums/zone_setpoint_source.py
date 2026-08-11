from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ZoneSetpointSource(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/zone.setpoint.source/000"""

    FromThermostat = auto()
    Learned = auto()

    @classmethod
    def default(cls) -> "ZoneSetpointSource":
        return cls.Learned

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "zone.setpoint.source"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
