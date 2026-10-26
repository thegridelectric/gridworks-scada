# Literal Enum:
#  - no additional values can be added over time.
#  - Sent as-is, not in hex symbol
from enum import auto

from gwsproto.enums.relay_event_base import RelayEventBase


class ChangeHeatPumpControl(RelayEventBase):
    """Sema: https://schemas.electricity.works/enums/change.heat.pump.control/000"""

    SwitchToTankAquastat = auto()
    SwitchToScada = auto()

    @classmethod
    def values(cls) -> list[str]:
        """
        Returns enum choices
        """
        return [elt.value for elt in cls]

    @classmethod
    def default(cls) -> "ChangeHeatPumpControl":
        return cls.SwitchToTankAquastat

    @classmethod
    def enum_name(cls) -> str:
        return "change.heat.pump.control"
