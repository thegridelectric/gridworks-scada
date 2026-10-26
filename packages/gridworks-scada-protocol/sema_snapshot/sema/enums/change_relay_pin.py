from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class ChangeRelayPin(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/change.relay.pin/000"""

    DeEnergize = auto()
    Energize = auto()

    @classmethod
    def default(cls) -> "ChangeRelayPin":
        return cls.DeEnergize

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "change.relay.pin"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
