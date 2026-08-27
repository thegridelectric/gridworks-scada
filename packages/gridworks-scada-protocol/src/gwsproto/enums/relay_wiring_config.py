from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class RelayWiringConfig(AslEnum):
    """Sema: https://schemas.electricity.works/enums/relay.wiring.config/000"""

    NormallyClosed = auto()
    NormallyOpen = auto()
    DoubleThrow = auto()

    @classmethod
    def default(cls) -> "RelayWiringConfig":
        return cls.NormallyClosed

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "relay.wiring.config"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
