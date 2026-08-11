from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ZoneCallCircuitEvent(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/zone.call.circuit.event/000"""

    WakeUp = auto()
    GoDormant = auto()
    Release = auto()
    ScadaHold = auto()
    ScadaCall = auto()
    ConfirmHeld = auto()
    ConfirmCalling = auto()
    ConfirmReleased = auto()
    ActuationFailed = auto()

    @classmethod
    def default(cls) -> "ZoneCallCircuitEvent":
        return cls.GoDormant

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "zone.call.circuit.event"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
