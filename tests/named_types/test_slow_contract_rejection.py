"""Tests slow.contract.rejection type, version 000"""

from gwsproto.enums import TaValidationState
from gwsproto.named_types import SlowContractRejection


def test_slow_contract_rejection_generated() -> None:
    d = {
        "FromGNodeAlias": "hw1.isone.me.versant.keene.beech.scada",
        "ContractId": "9d3b2a1c-8e7f-4a6b-b5c4-d3e2f1a0b9c8",
        "ValidationState": "UnValidated",
        "MessageCreatedMs": 1757300400250,
        "TypeName": "slow.contract.rejection",
        "Version": "000",
    }

    d2 = SlowContractRejection.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
    assert SlowContractRejection.model_validate(d).ValidationState == TaValidationState.UnValidated
