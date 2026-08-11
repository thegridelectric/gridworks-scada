from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ZoneCircuitRole(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/zone.circuit.role/000"""

    Baseload = auto()
    RapidResponse = auto()

    @classmethod
    def default(cls) -> "ZoneCircuitRole":
        return cls.Baseload

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "zone.circuit.role"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
