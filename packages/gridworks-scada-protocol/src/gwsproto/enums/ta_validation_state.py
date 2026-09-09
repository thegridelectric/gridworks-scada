# Versioned Enum:
#  - additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class TaValidationState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/ta.validation.state/000"""

    UnValidated = auto()
    ValidatedRealAssetAndGps = auto()
    ValidatedRealAssetIncorrectGps = auto()
    ValidatedSimulatedAsset = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "TaValidationState":
        return cls.UnValidated

    @classmethod
    def enum_name(cls) -> str:
        return "ta.validation.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
