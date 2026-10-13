from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class RebootPicos(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/reboot.picos/000"""

    RebootPicos = auto()

    @classmethod
    def default(cls) -> "RebootPicos":
        return cls.RebootPicos

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "reboot.picos"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
