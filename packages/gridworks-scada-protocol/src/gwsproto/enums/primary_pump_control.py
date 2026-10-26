from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class PrimaryPumpControl(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/primary.pump.control/000
    """

    HeatPump = auto()
    Scada = auto()

    @classmethod
    def default(cls) -> "PrimaryPumpControl":
        return cls.HeatPump

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "primary.pump.control"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
