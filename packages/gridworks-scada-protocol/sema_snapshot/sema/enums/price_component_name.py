from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class PriceComponentName(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/price.component.name/000"""

    Unknown = auto()
    WholesaleEnergy = auto()
    WholesaleCongestion = auto()
    WholesaleLoss = auto()
    Delivery = auto()
    CoincidentPeakTransmission = auto()
    CoincidentPeakCapacity = auto()

    @classmethod
    def default(cls) -> "PriceComponentName":
        return cls.Unknown

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "price.component.name"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
