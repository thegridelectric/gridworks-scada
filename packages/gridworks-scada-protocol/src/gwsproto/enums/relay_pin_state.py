from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class RelayPinState(AslEnum):
    """ASL: https://schemas.electricity.works/enums/relay.pin.state/000"""

    Energized = auto()
    DeEnergized = auto()


    @classmethod
    def default(cls) -> "RelayPinState":
        return cls.DeEnergized

    @classmethod
    def enum_name(cls) -> str:
        return "relay.pin.state"
    
    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def version(cls) -> str:
        return "000"
    