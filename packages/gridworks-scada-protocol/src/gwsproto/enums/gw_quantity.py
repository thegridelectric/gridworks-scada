from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class GwQuantity(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw1.quantity/000"""

    Unknown = auto()
    Unitless = auto()
    Power = auto()
    Energy = auto()
    Temperature = auto()
    FlowRate = auto()
    Volume = auto()
    Voltage = auto()
    Current = auto()
    Percent = auto()
    Frequency = auto()
    
    @classmethod
    def default(cls) -> "GwQuantity":
        return cls.Unknown

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.quantity"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
