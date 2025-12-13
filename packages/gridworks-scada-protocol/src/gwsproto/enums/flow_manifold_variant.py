from enum import auto
from typing import List

from gw.enums import GwStrEnum


class FlowManifoldVariant(GwStrEnum):
    """
    Values:
      - House0
      - House0Sieg

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#LocalControlTopState)
    """
    House0 = auto()
    House0Sieg = auto()


    @classmethod
    def default(cls) -> "FlowManifoldVariant":
        return cls.House0

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "flow.manifold.variant"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
