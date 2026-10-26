from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class ThermostatKind(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/thermostat.kind/000"""

    MechanicalDial = auto()
    HoneywellViaHubitat = auto()

    @classmethod
    def default(cls) -> "ThermostatKind":
        return cls.MechanicalDial

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "thermostat.kind"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
