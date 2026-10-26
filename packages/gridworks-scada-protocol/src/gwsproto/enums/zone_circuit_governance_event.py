from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ZoneCircuitGovernanceEvent(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/zone.circuit.governance.event/000"""

    WakeUp = auto()
    GoDormant = auto()
    SwitchToStatRules = auto()
    SwitchToOff = auto()
    SwitchToThermostatic = auto()

    @classmethod
    def default(cls) -> "ZoneCircuitGovernanceEvent":
        return cls.GoDormant

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "zone.circuit.governance.event"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
