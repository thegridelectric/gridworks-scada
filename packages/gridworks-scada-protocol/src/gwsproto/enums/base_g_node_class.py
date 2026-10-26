from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class BaseGNodeClass(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/base.g.node.class/000"""

    TerminalAsset = auto()
    LeafTransactiveNode = auto()
    ConnectivityNode = auto()
    MarketMaker = auto()
    Logical = auto()

    @classmethod
    def default(cls) -> "BaseGNodeClass":
        return cls.Logical

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "base.g.node.class"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
