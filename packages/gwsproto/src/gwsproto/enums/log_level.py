from enum import auto
from typing import List, Optional
from gw.enums import GwStrEnum


class LogLevel(GwStrEnum):
    """
    
    Values:
      - Critical
      - Error
      - Warning
      - Info
      - Debug
      - Trace

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#loglevel)
    """

    Critical = auto()
    Error = auto()
    Warning = auto()
    Info = auto()
    Debug = auto()
    Trace = auto()

    @classmethod
    def default(cls) -> "LogLevel":
        return cls.Info

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "log.level"

    @classmethod
    def enum_version(cls) -> str:
        return "000"

    @classmethod
    def highest_level(cls, levels: List["LogLevel"]) -> Optional["LogLevel"]:
        """
        Returns the highest level from a list of LogLevels.
        If the list is empty, returns None.
        """
        if not levels:
            return None
        return min(levels, key=lambda level: list(cls).index(level))
