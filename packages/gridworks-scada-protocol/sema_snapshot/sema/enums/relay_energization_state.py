from enum import IntEnum


class RelayEnergizationState(IntEnum):
    """Sema: https://schemas.electricity.works/enums/relay.energization.state/000"""

    DeEnergized = 0
    Energized = 1

    @classmethod
    def default(cls) -> "RelayEnergizationState":
        return cls.DeEnergized

    @classmethod
    def values(cls) -> list[int]:
        return [int(elt.value) for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "relay.energization.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
