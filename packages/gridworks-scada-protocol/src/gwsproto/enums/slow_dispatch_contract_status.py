from enum import auto
from gwsproto.enums.gw_str_enum import AslEnum
from typing import List

class SlowDispatchContractStatus(AslEnum):
    """Lifecycle status for dispatch contracts between LeafTransactiveNode 
    and SCADA, tracking creation through completion or termination.
    
    ASL: https://schemas.electricity.works/enums/gw1.slow.dispatch.contract.status/000
    """

    Created = auto()
    Received = auto() 
    Confirmed = auto()
    Active = auto()
    TerminatedByLtn = auto()
    TerminatedByScada = auto()
    CompletedUnknownOutcome = auto()
    CompletedSuccess = auto()
    CompletedFailureByScada = auto()
    CompletedFailureByLtn = auto()

    @classmethod
    def default(cls) -> "SlowDispatchContractStatus":
        return cls.Created

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "gw1.contract.status"

    @classmethod 
    def enum_version(cls) -> str:
        return "000"