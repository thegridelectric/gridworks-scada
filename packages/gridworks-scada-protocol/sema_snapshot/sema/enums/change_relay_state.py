from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class ChangeRelayState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/change.relay.state/000"""

    CloseRelay = auto()
    OpenRelay = auto()

    @classmethod
    def default(cls) -> "ChangeRelayState":
        return cls.OpenRelay

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "change.relay.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
