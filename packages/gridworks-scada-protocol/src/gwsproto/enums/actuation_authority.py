from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ActuationAuthority(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw1.actuation.authority/000"""

    Active = auto()
    Standby = auto()
    MonitorOnly = auto()

    @classmethod
    def default(cls) -> "ActuationAuthority":
        return cls.MonitorOnly

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.actuation.authority"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
