from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ZoneCallCircuitState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/zone.call.circuit.state/000"""

    Dormant = auto()
    Released = auto()
    TakingHold = auto()
    Held = auto()
    StartingCall = auto()
    Calling = auto()
    StoppingCall = auto()
    Releasing = auto()

    @classmethod
    def default(cls) -> "ZoneCallCircuitState":
        return cls.Released

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "zone.call.circuit.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
