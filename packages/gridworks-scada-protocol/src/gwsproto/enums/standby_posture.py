from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import SemaEnum


class StandbyPosture(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/gw.standby.posture/000"""

    MonitorOnly = auto()
    NoHeatingOrCooling = auto()

    @classmethod
    def default(cls) -> "StandbyPosture":
        return cls.MonitorOnly

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.standby.posture"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
