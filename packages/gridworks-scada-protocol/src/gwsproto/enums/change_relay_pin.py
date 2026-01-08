# Literal Enum:
#  - no additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gw.enums import GwStrEnum


class ChangeRelayPin(GwStrEnum):
    """
    Clarifies the event request sent to an internal multiplexing actor regarding a single relay
    on a relay board (energize or de-energize).
    """

    DeEnergize = auto()
    Energize = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "ChangeRelayPin":
        return cls.DeEnergize

    @classmethod
    def enum_name(cls) -> str:
        return "change.relay.pin"
