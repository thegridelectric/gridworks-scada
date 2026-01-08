from enum import auto

from gw.enums import GwStrEnum


class FsmActionType(GwStrEnum):
    """
    A list of the finite state machine Actions that a spaceheat node might take. An Action,
    in this context, is a side-effect of a state machine transition that impacts the real world
    (i.e., a relay is actuated).
    Values:
      - RelayPinSet
      - Analog010VSignalSet
      - Analog420maSignalSet

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#shfsmactiontype)
      - [More Info](https://gridworks-protocol.readthedocs.io/en/latest/finite-state-machines.html)
    """

    RelayPinSet = auto()
    Analog010VSignalSet = auto()
    Analog420maSignalSet = auto()

    @classmethod
    def default(cls) -> "FsmActionType":
        return cls.RelayPinSet

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "sh.fsm.action.type"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
