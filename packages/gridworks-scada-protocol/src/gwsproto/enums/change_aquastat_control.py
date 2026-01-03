# Literal Enum:
#  - no additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwproto.enums.relay_event_base import RelayEventBase


class ChangeAquastatControl(RelayEventBase):
    """
    A Finite State Machine action changing the function of an Aquastat Control
    """

    SwitchToBoiler = auto()
    SwitchToScada = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "ChangeAquastatControl":
        return cls.SwitchToBoiler

    @classmethod
    def enum_name(cls) -> str:
        return "change.aquastat.control"
