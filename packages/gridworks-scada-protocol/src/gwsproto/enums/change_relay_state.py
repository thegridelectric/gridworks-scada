# Literal Enum:
#  - no additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwsproto.enums.relay_event_base import RelayEventBase


class ChangeRelayState(RelayEventBase):
    """
    This is meant for relays in either NormallyOpen or NormallyClosed configuration (i.e. not
    configured as DoubleThrow). It provides the natural Finite State Machine actions that go
    along with simple.relay.state states of RelayOpen and RelayClosed. Open = PowerOff = 0 and
    Closed = PowerOn = 1
    """

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
