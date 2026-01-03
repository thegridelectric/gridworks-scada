"""Old School enum (uses integers)"""

from enum import Enum


class RelayEnergizationState(Enum):
    """
    The basic two-state enum for a double-throw relay where nothing is known about its energized/de-energized
    legs. This can only ever have two states. This is an old-school enum, where DeEnergized
    encodes 0 and Energized encodes 1.
    """

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
