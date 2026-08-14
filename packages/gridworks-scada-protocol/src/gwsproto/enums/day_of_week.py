from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class DayOfWeek(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/day.of.week/000"""

    Monday = auto()
    Tuesday = auto()
    Wednesday = auto()
    Thursday = auto()
    Friday = auto()
    Saturday = auto()
    Sunday = auto()

    @classmethod
    def default(cls) -> "DayOfWeek":
        return cls.Monday

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "day.of.week"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
