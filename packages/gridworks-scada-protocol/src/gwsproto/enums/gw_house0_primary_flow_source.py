from enum import auto
from typing import List

from gwsproto.enums.gw_str_enum import AslEnum


class GwHouse0PrimaryFlowSource(AslEnum):
    """ASL: https://schemas.electricity.works/enums/gw.house0.primary.flow.source/000

    How a House0 layout's primary-loop flow ("primary-flow") is obtained:
    Measured (a flow meter at the primary pump) or DerivedSiegSum (reconstructed
    from the Siegenthaler loop sensors, sieg-send + sieg-flow).
    """

    Measured = auto()
    DerivedSiegSum = auto()

    @classmethod
    def default(cls) -> "GwHouse0PrimaryFlowSource":
        return cls.Measured

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw.house0.primary.flow.source"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
