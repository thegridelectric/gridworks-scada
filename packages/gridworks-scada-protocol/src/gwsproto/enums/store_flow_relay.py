from enum import auto

from gwsproto.enums.gw_str_enum import SemaEnum


class StoreFlowRelay(SemaEnum):
    """Sema: https://schemas.electricity.works/enums/store.flow.relay/000
    """

    DischargingStore = auto()
    ChargingStore = auto()

    @classmethod
    def default(cls) -> "StoreFlowRelay":
        return cls.DischargingStore

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "store.flow.relay"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
