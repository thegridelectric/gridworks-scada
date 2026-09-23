from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class GwZoneEmitterType(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw.zone.emitter.type/000"""

    Other = auto()
    RadiantSlab = auto()
    FanCoil = auto()

    @classmethod
    def default(cls) -> "GwZoneEmitterType":
        return cls.Other

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.zone.emitter.type"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
