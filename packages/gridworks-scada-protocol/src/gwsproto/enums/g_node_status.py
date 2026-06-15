from enum import auto

from gwsproto.enums.gw_str_enum import AslEnum


class GNodeStatus(AslEnum):
    """ASL: https://schemas.electricity.works/enums/g.node.status/000"""

    Pending = auto()
    Active = auto()
    Suspended = auto()
    PermanentlyDeactivated = auto()

    @classmethod
    def default(cls) -> "GNodeStatus":
        return cls.Pending

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "g.node.status"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
