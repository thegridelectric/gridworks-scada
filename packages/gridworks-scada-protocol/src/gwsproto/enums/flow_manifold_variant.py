from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class FlowManifoldVariant(AslEnum):
    """ASL: https://schemas.electricity.works/enums/flow.manifold.variant/001"""
    House0 = auto()
    House0Sieg = auto()
    NolanHouse = auto()


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
        return "001"
