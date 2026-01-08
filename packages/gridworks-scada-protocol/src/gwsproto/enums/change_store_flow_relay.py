from enum import auto

from gw.enums import GwStrEnum


class ChangeStoreFlowRelay(GwStrEnum):
    """
    Events that trigger changing StoreFlowDirection finite state machine
    Values:
      - DischargeStore
      - ChargeStore

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#changestoreflowrelay)
    """

    DischargeStore = auto()
    ChargeStore = auto()

    @classmethod
    def default(cls) -> "ChangeStoreFlowRelay":
        return cls.DischargeStore

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "change.store.flow.relay"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
