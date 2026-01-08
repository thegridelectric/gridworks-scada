# Literal Enum:
#  - no additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gw.enums import GwStrEnum


class RelayClosedOrOpen(GwStrEnum):
    """
    These are fsm states (as opposed to readings from a pin).
    """

    RelayClosed = auto()
    RelayOpen = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "RelayClosedOrOpen":
        return cls.RelayClosed

    @classmethod
    def enum_name(cls) -> str:
        return "relay.closed.or.open"
