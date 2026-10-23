from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class AquastatControlState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/aquastat.control.state/000"""

    Boiler = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "AquastatControlState":
        return cls.Boiler

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "aquastat.control.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
