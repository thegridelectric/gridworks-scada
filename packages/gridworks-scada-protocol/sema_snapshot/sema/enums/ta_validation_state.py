from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class TaValidationState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/ta.validation.state/000"""

    UnValidated = auto()
    ValidatedRealAssetAndGps = auto()
    ValidatedRealAssetIncorrectGps = auto()
    ValidatedSimulatedAsset = auto()

    @classmethod
    def default(cls) -> "TaValidationState":
        return cls.UnValidated

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "ta.validation.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
