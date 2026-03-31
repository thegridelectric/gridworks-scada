# Literal Enum:
#  - no additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwsproto.enums.relay_event_base import RelayEventBase


class ChangeRelayState(RelayEventBase):
    """Sema: https://schemas.electricity.works/enums/change.relay.state/000"""

    CloseRelay = auto()
    OpenRelay = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "ChangeRelayState":
        return cls.OpenRelay

    @classmethod
    def enum_name(cls) -> str:
        return "change.relay.state"
