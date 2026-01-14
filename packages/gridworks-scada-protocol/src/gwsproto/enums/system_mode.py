from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class SystemMode(AslEnum):
    """
    System operational mode for HVAC control.

    ASL: https://schemas.electricity.works/enums/gw1.system.mode/000
    """

    Heating = auto() # Actively managing heating operations
    Standby = auto() # Not heating, relays managed to prevent oil boiler, heat pump etc from coming on
    MonitorOnly = auto() # no relays energized

    @classmethod
    def default(cls) -> "SystemMode":
        return cls.Heating

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.system.mode"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
