from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class Quantity(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw1.quantity/003"""

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
    Time = auto()
    WindSpeed = auto()
    Irradiance = auto()
    Currency = auto()

    @classmethod
    def default(cls) -> "Quantity":
        return cls.Unknown

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.quantity"

    @classmethod
    def enum_version(cls) -> str:
        return "003"
