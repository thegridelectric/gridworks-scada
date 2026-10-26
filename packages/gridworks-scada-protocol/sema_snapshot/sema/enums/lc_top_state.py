from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class LcTopState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw2.lc.top.state/000"""

    Dormant = auto()
    Normal = auto()
    ScadaBlind = auto()
    Standby = auto()
    InBackup = auto()
    ColdOverride = auto()

    @classmethod
    def default(cls) -> "LcTopState":
        return cls.Dormant

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw2.lc.top.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
