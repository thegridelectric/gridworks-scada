from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ZoneCircuitGovernanceState(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/zone.circuit.governance.state/000"""

    Dormant = auto()
    StatRules = auto()
    Off = auto()
    ScadaThermostatic = auto()

    @classmethod
    def default(cls) -> "ZoneCircuitGovernanceState":
        return cls.Dormant

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "zone.circuit.governance.state"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
