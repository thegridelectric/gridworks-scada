from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import DispatchRefusalReason
from sema_snapshot.sema.enums import SlowDispatchContractStatus
from sema_snapshot.sema.property_format import DecimalDigit
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.types.slow_dispatch_contract import SlowDispatchContract


class SlowContractHeartbeat(SemaType):
    """Sema: https://schemas.electricity.works/types/slow.contract.heartbeat/002"""

    from_node: SpaceheatName
    contract: SlowDispatchContract
    previous_status: SlowDispatchContractStatus | None = None
    status: SlowDispatchContractStatus
    message_created_ms: UTCMilliseconds
    cause: str | None = None
    reason: DispatchRefusalReason | None = None
    is_authoritative: bool
    watt_hours_used: StrictInt | None = None
    my_digit: DecimalDigit
    your_last_digit: DecimalDigit | None = None
    signed_proof: str
    type_name: Literal["slow.contract.heartbeat"] = "slow.contract.heartbeat"
    version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "SlowContractHeartbeat":
        """
        Axiom 1: CreatedWithinTenSeconds
        If Status is Created, MessageCreatedMs / 1000 SHALL be no more than 10 seconds
        after Contract.StartS.
        """
        if self.status is SlowDispatchContractStatus.Created:
            late_s = self.message_created_ms / 1000 - self.contract.start_s
            if late_s > 10:
                raise ValueError(
                    "Axiom 1 (CreatedWithinTenSeconds) failed: Created must be "
                    f"within 10 s of Contract.StartS, got {round(late_s, 2)} s."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "SlowContractHeartbeat":
        """
        Axiom 2: StatusAuthority
        a. If Status is Created, Confirmed or TerminatedByLtn, FromNode SHALL be ltn and
           IsAuthoritative SHALL be true.
        b. If Status is Received or TerminatedByScada, FromNode SHALL be s and
           IsAuthoritative SHALL be true.
        c. If Status is CompletedSuccess, CompletedFailureByLtn or
           CompletedFailureByScada, IsAuthoritative SHALL be false.
        """
        status = SlowDispatchContractStatus
        if self.status in (status.Created, status.Confirmed, status.TerminatedByLtn):
            if self.from_node != "ltn" or not self.is_authoritative:
                raise ValueError(
                    f"Axiom 2 (StatusAuthority) failed: {self.status.value} is "
                    "stated only by ltn, authoritatively."
                )
        if self.status in (status.Received, status.TerminatedByScada):
            if self.from_node != "s" or not self.is_authoritative:
                raise ValueError(
                    f"Axiom 2 (StatusAuthority) failed: {self.status.value} is "
                    "stated only by s, authoritatively."
                )
        if self.status in (
            status.CompletedSuccess,
            status.CompletedFailureByLtn,
            status.CompletedFailureByScada,
        ):
            if self.is_authoritative:
                raise ValueError(
                    f"Axiom 2 (StatusAuthority) failed: {self.status.value} is a "
                    "claim; IsAuthoritative must be false."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "SlowContractHeartbeat":
        """
        Axiom 3: CausePresence
        Cause SHALL be present if and only if Status is TerminatedByLtn, TerminatedByScada,
        CompletedUnknownOutcome, CompletedFailureByLtn or CompletedFailureByScada.
        """
        status = SlowDispatchContractStatus
        needs_cause = self.status in (
            status.TerminatedByLtn,
            status.TerminatedByScada,
            status.CompletedUnknownOutcome,
            status.CompletedFailureByLtn,
            status.CompletedFailureByScada,
        )
        if needs_cause and self.cause is None:
            raise ValueError(
                f"Axiom 3 (CausePresence) failed: {self.status.value} requires Cause."
            )
        if not needs_cause and self.cause is not None:
            raise ValueError(
                f"Axiom 3 (CausePresence) failed: {self.status.value} forbids Cause."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "SlowContractHeartbeat":
        """
        Axiom 4: FromNodeIsParty
        FromNode SHALL be s or ltn.
        """
        if self.from_node not in ("s", "ltn"):
            raise ValueError(
                "Axiom 4 (FromNodeIsParty) failed: FromNode must be s or ltn, "
                f"got {self.from_node}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> "SlowContractHeartbeat":
        """
        Axiom 5: ScadaReportsWattHours
        WattHoursUsed SHALL be present if and only if FromNode is s.
        """
        if self.from_node == "s" and self.watt_hours_used is None:
            raise ValueError(
                "Axiom 5 (ScadaReportsWattHours) failed: s must send WattHoursUsed."
            )
        if self.from_node != "s" and self.watt_hours_used is not None:
            raise ValueError(
                "Axiom 5 (ScadaReportsWattHours) failed: only s sends WattHoursUsed."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> "SlowContractHeartbeat":
        """
        Axiom 6: ReasonOnScadaTermination
        Reason SHALL be present if and only if Status is TerminatedByScada.
        """
        terminated = self.status is SlowDispatchContractStatus.TerminatedByScada
        if terminated and self.reason is None:
            raise ValueError(
                "Axiom 6 (ReasonOnScadaTermination) failed: TerminatedByScada "
                "requires Reason."
            )
        if not terminated and self.reason is not None:
            raise ValueError(
                "Axiom 6 (ReasonOnScadaTermination) failed: Reason only on "
                "TerminatedByScada."
            )
        return self
