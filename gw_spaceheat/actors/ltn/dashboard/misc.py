from enum import auto
from enum import StrEnum


class UpdateSources(StrEnum):
    Initialization = auto()
    Snapshot = auto()
    Power = auto()

