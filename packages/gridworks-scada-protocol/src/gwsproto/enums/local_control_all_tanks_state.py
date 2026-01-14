from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class LocalControlAllTanksState(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.local.control.all.tanks.state/000"""

    Initializing = auto()
    HpOnStoreOff = auto()
    HpOnStoreCharge = auto()
    HpOffStoreOff = auto()
    HpOffStoreDischarge = auto()
    Dormant = auto()

    @classmethod
    def default(cls) -> "LocalControlAllTanksState":
        return cls.Initializing

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.local.control.all.tanks.state"

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def version(cls) -> str:
        return "000"