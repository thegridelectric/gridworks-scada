from typing import Optional, Literal
from gwsproto.property_format import  UTCMilliseconds, SpaceheatName
from pydantic import BaseModel, field_validator, model_validator
from gwsproto.enums import SlowDispatchContractStatus
from gwsproto.named_types import SlowDispatchContract
from typing_extensions import Self

SCADA_SH_NODE_NAME = "s"
LTN_SH_NODE_NAME = "ltn"
class SlowContractHeartbeat(BaseModel):
    """Base class for contract lifecycle messages
    ASL: https://schemas.electricity.works/types/slow.contract.heartbeat/001
    """
    FromNode: SpaceheatName # either "ltn" or "s", for Ltn or Scada
    Contract: SlowDispatchContract
    PreviousStatus: Optional[SlowDispatchContractStatus] = None
    Status: SlowDispatchContractStatus
    MessageCreatedMs: UTCMilliseconds
    Cause: Optional[str] = None
    IsAuthoritative: bool = True
    WattHoursUsed: Optional[int] = None
    MyDigit: int
    YourLastDigit: Optional[int] = None
    SignedProof: str = "signed_proof_stub"
    TypeName: Literal["slow.contract.heartbeat"] = "slow.contract.heartbeat"
    Version: Literal["001"] = "001"


    def contract_grace_period_minutes(self) -> Literal[5]:
        return 5

    def grace_period_end_s(self) -> int:
        """ 5 minutes after the ContractEndS unless the contract
        was terminated, in which case 5 minutes after termination
        """
        contract_done_s = self.Contract.contract_end_s()
        if self.Status in [SlowDispatchContractStatus.TerminatedByLtn, SlowDispatchContractStatus.TerminatedByScada]:
            contract_done_s = int(self.MessageCreatedMs / 1000)
        return contract_done_s + self.contract_grace_period_minutes() * 60
        # TODO: Add a test for this logic

    @model_validator(mode="after")
    def _check_axiom_1(self) -> Self:
        """Axiom 1: Contracts must be created no later 
        than 10 seconds after StartS"""
        if self.Status in [SlowDispatchContractStatus.Created]:
            time_s = self.MessageCreatedMs / 1000
            if time_s > self.Contract.StartS + 10:
                raise ValueError(
                    f"Axiom 2: Must be {self.Status.value} within 10 seconds of Contract Start. Got {round(time_s - self.Contract.StartS, 2)}"
                )
        return self
    
    @model_validator(mode='after')
    def _check_axiom_2(self) -> Self:
        """Axiom 2 Check authority: Validate authority for status changes"""
        
        # Only Atn can create or confirm
        if self.Status in [SlowDispatchContractStatus.Created, SlowDispatchContractStatus.Confirmed, SlowDispatchContractStatus.TerminatedByLtn]:
            if self.FromNode != LTN_SH_NODE_NAME:
                raise ValueError(f"Only LeafTransactiveNode can set status {self.Status}")
            if not self.IsAuthoritative:
                raise ValueError("LeafTransactiveNode IsAuthoritative for Created and Confirmed!")
        # Only Scada can mark as received
        if self.Status in [SlowDispatchContractStatus.Received, SlowDispatchContractStatus.TerminatedByScada]:
            if self.FromNode != SCADA_SH_NODE_NAME:
                raise ValueError(f"Only Scada can set status {self.Status}")
            if not self.IsAuthoritative:
                raise ValueError("Scada IsAuthoritative for Received!")
        # Active/CompletedSuccess/CompletedFailure are for umpire only
        # For now, treat these as claims by participants
        if self.Status in [SlowDispatchContractStatus.CompletedSuccess,
                          SlowDispatchContractStatus.CompletedFailureByLtn,
                          SlowDispatchContractStatus.CompletedFailureByScada]:
            # Later the umpire will enforce these
            # For now just let participants publish their view
            if self.IsAuthoritative:
                raise ValueError(f"{self.FromNode} is NOT Authoritative for {self.Status}")

        return self

    @model_validator(mode='after')
    def check_axiom_3(self) -> Self:
        """Axiom 3: Cause required for and limited to Terminated and CompletedFailure/Unknown status"""
        needs_cause = self.Status in [SlowDispatchContractStatus.TerminatedByLtn,
                                      SlowDispatchContractStatus.TerminatedByScada, 
                                      SlowDispatchContractStatus.CompletedUnknownOutcome,
                                      SlowDispatchContractStatus.CompletedFailureByLtn,
                                      SlowDispatchContractStatus.CompletedFailureByScada]
        has_cause = self.Cause is not None

        if needs_cause and not has_cause:
            raise ValueError(f"Cause is required for {needs_cause}")
        if not needs_cause and has_cause:
            raise ValueError(f"Cause only valid for {needs_cause} status")
        return self

    @field_validator("FromNode")
    @classmethod
    def _check_from_node(cls, v: str) -> str:
        """
        Axiom 4: FromNode should be 's' (Scada) or 'ltn' (LeafTransactiveNode)
        """
        if v not in [LTN_SH_NODE_NAME, SCADA_SH_NODE_NAME]:
            raise ValueError(
                f"Axiom 4: FromNode should be 's' (Scada) or 'ltn' (LeafTransactiveNode). Got {v}"
            )
        return v

    @model_validator(mode='after')
    def check_axiom_5(self) -> Self:
        """
        Future: Validate signed proof. 
        By including YourLastDigit and the previous message's SignedProof,
        this creates an unbreakable chain where:
          - Each party must reference the exact signature from their counterparty's last message
          - The digits create a crosslinked sequence that must match on both sides
          - The signatures create a cryptographic chain that can't be spoofed by one side after-the-fact
        sign({
            "ContractId": "c3cd6c8d-e8d8-4875-8f7b-d3ea13c28693", 
            "FromNode": "ltn",
            "Status": "Active",
            "MessageCreatedMs": 1740425972511,
            "MyDigit": 3,
            "YourLastDigit": 7,
            "PrevSignedProof": "algo_sig_xyz..."
        })
        Currently accepts placeholder that follows basic Algorand message pack format.
        """
        return self

    @model_validator(mode='after')
    def check_axiom_6(self) -> Self:
        """Axiom 6: check digits"""
        if self.MyDigit not in range(10):
            raise ValueError(f"MyDigit must be in range(10) not {self.MyDigit}")
        if self.YourLastDigit:
            if self.YourLastDigit not in range(10):
                raise ValueError(f"YourLastDigit must be in range(10) not {self.YourLastDigit}")
        return self

    @model_validator(mode='after')
    def check_axiom_7(self) -> Self:
        """Axiom 7: Scada (and only Scada) sends WattHoursUsed"""
        if self.FromNode == SCADA_SH_NODE_NAME:
            if self.WattHoursUsed is None:
                raise ValueError("Scada sends WattHoursUsed")
        else:
            if self.WattHoursUsed:
                raise ValueError("Only Scada sends WattHoursUsed")
        return self




