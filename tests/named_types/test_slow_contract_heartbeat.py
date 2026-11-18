"""Tests slow.contract.heartbeat type, version 003"""

from gwsproto.enums import DispatchRefusalReason
from gwsproto.named_types import SlowContractHeartbeat
from gwsproto.named_types.slow_contract_heartbeat import SIGNED_PROOF_STUB

from tests.named_types.sema_oracle import assert_conforms, assert_refused

CONTRACT = {
    "ScadaAlias": "hw1.isone.me.versant.keene.beech.scada",
    "StartS": 1757300400,
    "DurationMinutes": 60,
    "AvgPowerWatts": 3000,
    "ContractId": "9d3b2a1c-8e7f-4a6b-b5c4-d3e2f1a0b9c8",
    "DispatchTerms": "dispatch.terms.first.isone.hack",
    "TypeName": "slow.dispatch.contract",
    "Version": "001",
}

CREATED = {
    "FromNode": "ltn",
    "Contract": CONTRACT,
    "Status": "Created",
    "MessageCreatedMs": 1757300402000,
    "IsAuthoritative": True,
    "MyDigit": 3,
    "SignedProof": "signed_proof_stub",
    "TypeName": "slow.contract.heartbeat",
    "Version": "003",
}

TERMINATED_BY_SCADA = {
    "FromNode": "s",
    "Contract": CONTRACT,
    "PreviousStatus": "Active",
    "Status": "TerminatedByScada",
    "MessageCreatedMs": 1757301000000,
    "Cause": "house went cold",
    "Reason": "ServiceContractBroken",
    "IsAuthoritative": True,
    "WattHoursUsed": 1200,
    "MyDigit": 7,
    "YourLastDigit": 3,
    "SignedProof": "signed_proof_stub",
    "TypeName": "slow.contract.heartbeat",
    "Version": "003",
}


def test_slow_contract_heartbeat_generated() -> None:
    for d in (CREATED, TERMINATED_BY_SCADA):
        hb = SlowContractHeartbeat.model_validate(d)
        assert hb.model_dump(by_alias=True, exclude_none=True) == d
        assert_conforms(hb)
    hb = SlowContractHeartbeat.model_validate(TERMINATED_BY_SCADA)
    assert hb.Reason is DispatchRefusalReason.ServiceContractBroken


def test_slow_contract_heartbeat_digits_are_decimal_digits() -> None:
    for bad in (10, -1, "3", 3.0):
        assert_refused(SlowContractHeartbeat, dict(CREATED, MyDigit=bad))
        assert_refused(SlowContractHeartbeat, dict(CREATED, YourLastDigit=bad))


def test_slow_contract_heartbeat_axiom_1_created_late() -> None:
    assert_refused(
        SlowContractHeartbeat,
        dict(CREATED, MessageCreatedMs=1757300411000),
        match="Axiom 1 \\(CreatedWithinTenSeconds\\)",
    )


def test_slow_contract_heartbeat_axiom_2_a_created_by_scada() -> None:
    assert_refused(
        SlowContractHeartbeat,
        dict(CREATED, FromNode="s", WattHoursUsed=0),
        match="Axiom 2 \\(StatusAuthority, clause a\\)",
    )
    assert_refused(
        SlowContractHeartbeat,
        dict(CREATED, IsAuthoritative=False),
        match="Axiom 2 \\(StatusAuthority, clause a\\)",
    )


def test_slow_contract_heartbeat_axiom_2_b_terminated_by_scada_from_ltn() -> None:
    d = dict(TERMINATED_BY_SCADA, FromNode="ltn")
    del d["WattHoursUsed"]
    assert_refused(SlowContractHeartbeat, d, match="Axiom 2 \\(StatusAuthority, clause b\\)")


def test_slow_contract_heartbeat_axiom_2_c_authoritative_completion() -> None:
    d = dict(TERMINATED_BY_SCADA, Status="CompletedSuccess")
    del d["Cause"], d["Reason"]
    assert_refused(SlowContractHeartbeat, d, match="Axiom 2 \\(StatusAuthority, clause c\\)")
    assert_conforms(
        SlowContractHeartbeat.model_validate(dict(d, IsAuthoritative=False))
    )


def test_slow_contract_heartbeat_axiom_3_cause_presence() -> None:
    d = dict(TERMINATED_BY_SCADA)
    del d["Cause"]
    assert_refused(SlowContractHeartbeat, d, match="Axiom 3 \\(CausePresence\\)")
    assert_refused(
        SlowContractHeartbeat,
        dict(CREATED, Cause="no reason"),
        match="Axiom 3 \\(CausePresence\\)",
    )


def test_slow_contract_heartbeat_axiom_4_from_node_not_a_party() -> None:
    assert_refused(
        SlowContractHeartbeat,
        dict(CREATED, Status="CompletedUnknownOutcome", FromNode="umpire", Cause="x"),
        match="Axiom 4 \\(FromNodeIsParty\\)",
    )


def test_slow_contract_heartbeat_axiom_5_watt_hours_presence() -> None:
    d = dict(TERMINATED_BY_SCADA)
    del d["WattHoursUsed"]
    assert_refused(
        SlowContractHeartbeat, d, match="Axiom 5 \\(ScadaReportsWattHours\\)"
    )
    assert_refused(
        SlowContractHeartbeat,
        dict(CREATED, WattHoursUsed=0),
        match="Axiom 5 \\(ScadaReportsWattHours\\)",
    )


def test_slow_contract_heartbeat_axiom_6_reason_presence() -> None:
    d = dict(TERMINATED_BY_SCADA)
    del d["Reason"]
    assert_refused(
        SlowContractHeartbeat, d, match="Axiom 6 \\(ReasonOnScadaTermination\\)"
    )
    assert_refused(
        SlowContractHeartbeat,
        dict(CREATED, Reason="OperatorHold"),
        match="Axiom 6 \\(ReasonOnScadaTermination\\)",
    )


def test_authority_and_proof_required_on_decode_defaulted_on_construction() -> None:
    for field in ("IsAuthoritative", "SignedProof"):
        assert_refused(
            SlowContractHeartbeat,
            {k: v for k, v in CREATED.items() if k != field},
            match=field,
        )
    kwargs = {
        k: v for k, v in CREATED.items() if k not in ("IsAuthoritative", "SignedProof")
    }
    hb = SlowContractHeartbeat(**kwargs)
    assert hb.IsAuthoritative is True
    assert hb.SignedProof == SIGNED_PROOF_STUB
    assert_conforms(hb)


AMENDED = {
    "FromNode": "ltn",
    "Contract": dict(CONTRACT, AvgPowerWatts=4200),
    "PreviousStatus": "Confirmed",
    "Status": "Amended",
    "MessageCreatedMs": 1757300431000,
    "Cause": "Final price 72.5 USD/MWh, offer raised",
    "IsAuthoritative": True,
    "MyDigit": 5,
    "YourLastDigit": 8,
    "SignedProof": "signed_proof_stub",
    "TypeName": "slow.contract.heartbeat",
    "Version": "003",
}


def test_the_ltn_amends_with_a_cause() -> None:
    hb = SlowContractHeartbeat.model_validate(AMENDED)
    assert hb.model_dump(by_alias=True, exclude_none=True) == AMENDED
    assert_conforms(hb)


def test_slow_contract_heartbeat_axiom_2_a_amended_by_scada() -> None:
    assert_refused(
        SlowContractHeartbeat,
        dict(AMENDED, FromNode="s", WattHoursUsed=120),
        match="Axiom 2 \\(StatusAuthority, clause a\\)",
    )


def test_slow_contract_heartbeat_axiom_3_amended_without_cause() -> None:
    d = dict(AMENDED)
    del d["Cause"]
    assert_refused(SlowContractHeartbeat, d, match="Axiom 3 \\(CausePresence\\)")
