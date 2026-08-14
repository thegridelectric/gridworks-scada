from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ServiceMode(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw1.service.mode/000"""

    Heating = auto()
    Cooling = auto()

    @classmethod
    def default(cls) -> "ServiceMode":
        return cls.Heating

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.service.mode"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
