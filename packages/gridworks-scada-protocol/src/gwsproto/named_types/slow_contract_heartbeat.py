from typing import Literal, Optional

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import DispatchRefusalReason, SlowDispatchContractStatus
from gwsproto.named_types.slow_dispatch_contract import SlowDispatchContract
from gwsproto.property_format import DecimalDigit, SpaceheatName, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType

SCADA_SH_NODE_NAME = "s"
LTN_SH_NODE_NAME = "ltn"


class SlowContractHeartbeat(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/slow.contract.heartbeat/002"""

    FromNode: SpaceheatName
    Contract: SlowDispatchContract
    PreviousStatus: Optional[SlowDispatchContractStatus] = None
    Status: SlowDispatchContractStatus
    MessageCreatedMs: UTCMilliseconds
    Cause: Optional[str] = None
    Reason: Optional[DispatchRefusalReason] = None
    IsAuthoritative: bool = True
    WattHoursUsed: Optional[int] = None
    MyDigit: DecimalDigit
    YourLastDigit: Optional[DecimalDigit] = None
    SignedProof: str = "signed_proof_stub"
    TypeName: Literal["slow.contract.heartbeat"] = "slow.contract.heartbeat"
    Version: Literal["002"] = "002"

    def contract_grace_period_minutes(self) -> Literal[5]:
        return 5

    def grace_period_end_s(self) -> int:
        """5 minutes after the ContractEndS unless the contract
        was terminated, in which case 5 minutes after termination
        """
        contract_done_s = self.Contract.contract_end_s()
        if self.Status in [
            SlowDispatchContractStatus.TerminatedByLtn,
            SlowDispatchContractStatus.TerminatedByScada,
        ]:
            contract_done_s = int(self.MessageCreatedMs / 1000)
        return contract_done_s + self.contract_grace_period_minutes() * 60

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: CreatedWithinTenSeconds.
        If Status is Created, MessageCreatedMs / 1000 SHALL be no more than
        10 seconds after Contract.StartS.
        """
        if self.Status is SlowDispatchContractStatus.Created:
            time_s = self.MessageCreatedMs / 1000
            if time_s > self.Contract.StartS + 10:
                raise ValueError(
                    "Axiom 1 (CreatedWithinTenSeconds) failed: Created must be "
                    "within 10 seconds of Contract.StartS; got "
                    f"{round(time_s - self.Contract.StartS, 2)} s"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: StatusAuthority.
        a. If Status is Created, Confirmed or TerminatedByLtn, FromNode SHALL
           be ltn and IsAuthoritative SHALL be true.
        b. If Status is Received or TerminatedByScada, FromNode SHALL be s
           and IsAuthoritative SHALL be true.
        c. If Status is CompletedSuccess, CompletedFailureByLtn or
           CompletedFailureByScada, IsAuthoritative SHALL be false.
        """
        if self.Status in [
            SlowDispatchContractStatus.Created,
            SlowDispatchContractStatus.Confirmed,
            SlowDispatchContractStatus.TerminatedByLtn,
        ]:
            if self.FromNode != LTN_SH_NODE_NAME or not self.IsAuthoritative:
                raise ValueError(
                    f"Axiom 2 (StatusAuthority) failed: {self.Status} requires "
                    "FromNode ltn and IsAuthoritative true; got FromNode "
                    f"{self.FromNode}, IsAuthoritative {self.IsAuthoritative}"
                )
        if self.Status in [
            SlowDispatchContractStatus.Received,
            SlowDispatchContractStatus.TerminatedByScada,
        ]:
            if self.FromNode != SCADA_SH_NODE_NAME or not self.IsAuthoritative:
                raise ValueError(
                    f"Axiom 2 (StatusAuthority) failed: {self.Status} requires "
                    "FromNode s and IsAuthoritative true; got FromNode "
                    f"{self.FromNode}, IsAuthoritative {self.IsAuthoritative}"
                )
        if self.Status in [
            SlowDispatchContractStatus.CompletedSuccess,
            SlowDispatchContractStatus.CompletedFailureByLtn,
            SlowDispatchContractStatus.CompletedFailureByScada,
        ]:
            if self.IsAuthoritative:
                raise ValueError(
                    f"Axiom 2 (StatusAuthority) failed: {self.Status} requires "
                    "IsAuthoritative false"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: CausePresence.
        Cause SHALL be present if and only if Status is TerminatedByLtn,
        TerminatedByScada, CompletedUnknownOutcome, CompletedFailureByLtn or
        CompletedFailureByScada.
        """
        needs_cause = self.Status in [
            SlowDispatchContractStatus.TerminatedByLtn,
            SlowDispatchContractStatus.TerminatedByScada,
            SlowDispatchContractStatus.CompletedUnknownOutcome,
            SlowDispatchContractStatus.CompletedFailureByLtn,
            SlowDispatchContractStatus.CompletedFailureByScada,
        ]
        if needs_cause != (self.Cause is not None):
            raise ValueError(
                "Axiom 3 (CausePresence) failed: Cause is present iff Status is "
                "a termination, failure or unknown outcome; got Status "
                f"{self.Status}, Cause {self.Cause!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: FromNodeIsParty.
        FromNode SHALL be s or ltn.
        """
        if self.FromNode not in [LTN_SH_NODE_NAME, SCADA_SH_NODE_NAME]:
            raise ValueError(
                "Axiom 4 (FromNodeIsParty) failed: FromNode must be s or ltn; "
                f"got {self.FromNode}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: ScadaReportsWattHours.
        WattHoursUsed SHALL be present if and only if FromNode is s.
        """
        if (self.FromNode == SCADA_SH_NODE_NAME) != (self.WattHoursUsed is not None):
            raise ValueError(
                "Axiom 5 (ScadaReportsWattHours) failed: WattHoursUsed is present "
                f"iff FromNode is s; got FromNode {self.FromNode}, "
                f"WattHoursUsed {self.WattHoursUsed}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> Self:
        """
        Axiom 6: ReasonOnScadaTermination.
        Reason SHALL be present if and only if Status is TerminatedByScada.
        """
        terminated_by_scada = (
            self.Status is SlowDispatchContractStatus.TerminatedByScada
        )
        if terminated_by_scada != (self.Reason is not None):
            raise ValueError(
                "Axiom 6 (ReasonOnScadaTermination) failed: Reason is present iff "
                f"Status is TerminatedByScada; got Status {self.Status}, "
                f"Reason {self.Reason}"
            )
        return self
