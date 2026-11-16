"""Tests dispatch.terms.first.isone.hack type, version 000: a constant, so
every instance is the same JSON."""

from gwsproto.named_types import DispatchTermsFirstIsoneHack
from tests.named_types.sema_oracle import assert_conforms, assert_refused

TERMS = {
    "MarketMakerAlias": "hw1.isone.me.versant.keene",
    "MarketProductName": "rt60gate1",
    "FinalDeadlineS": 240,
    "AmendmentsAllowed": 1,
    "BindingStage": "Final",
    "ProvisionalAction": "ReduceOnly",
    "TypeName": "dispatch.terms.first.isone.hack",
    "Version": "000",
}


def test_every_instance_is_the_same_json() -> None:
    assert DispatchTermsFirstIsoneHack().model_dump(by_alias=True) == TERMS
    assert DispatchTermsFirstIsoneHack.model_validate(TERMS).model_dump(by_alias=True) == TERMS
    assert_conforms(DispatchTermsFirstIsoneHack())


def test_another_value_is_not_these_terms() -> None:
    assert_refused(DispatchTermsFirstIsoneHack, dict(TERMS, FinalDeadlineS=300), match="FinalDeadlineS")
