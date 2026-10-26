from enum import auto

from sema_snapshot.sema.enums.gw_str_enum import SemaEnum


class RelayClosedOrOpen(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/relay.closed.or.open/000"""

    RelayClosed = auto()
    RelayOpen = auto()

    @classmethod
    def default(cls) -> "RelayClosedOrOpen":
        return cls.RelayClosed

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "relay.closed.or.open"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
