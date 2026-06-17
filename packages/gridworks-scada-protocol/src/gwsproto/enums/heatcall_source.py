from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class HeatcallSource(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/heatcall.source/000
    """

    WallThermostat = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "HeatcallSource":
        return cls.WallThermostat

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "heatcall.source"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
