from enum import auto
from gw.enums import GwStrEnum
from typing import List

class ContractStatus(GwStrEnum):
    """Status enum for tracking contract lifecycle

    Values:
      - Created # Initial contract proposal
      - Received # Counter-party acknowledges receipt
      - Confirmed # Counter-party accepts terms
      - Active # Contract currently in force
      - TerminatedByAtn # Contract ended early by Atn
      - TerminatedByScada # Contract ended early by Scada
      - CompletedSuccess # Contract ran full duration and terms met
      - CompletedFailureByScada # Contract ran full duration, terms not met by Scada
      - CompletedFailureByAtn # Contract ran full duration, terms not met by Atn

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
    """
    Created = auto()
    Received = auto() 
    Confirmed = auto()
    Active = auto()
    TerminatedByAtn = auto()
    TerminatedByScada = auto()
    CompletedUnknownOutcome = auto()
    CompletedSuccess = auto()
    CompletedFailureByScada = auto()
    CompletedFailureByAtn = auto()

    @classmethod
    def default(cls) -> "ContractStatus":
        return cls.Created

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "contract.status"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"