"""Old School enum (uses integers)"""

from enum import Enum


class RelayEnergizationState(Enum):

    DeEnergized = 0
    Energized = 1

    @classmethod
    def values(cls) -> list[int]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "RelayEnergizationState":
        return cls.DeEnergized

    @classmethod
    def enum_name(cls) -> str:
        return "relay.energization.state"
