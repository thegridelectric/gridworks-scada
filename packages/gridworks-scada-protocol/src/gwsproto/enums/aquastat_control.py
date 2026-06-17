from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class AquastatControl(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/aquastat.control.state/000
    """

    Boiler = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "AquastatControl":
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
