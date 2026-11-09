"""flo.refusal 000: the twin agrees with the snapshot on the word's example,
with and without the optional Detail."""

import copy

from gwsproto.enums import FloRefusalReason
from gwsproto.named_types import FloRefusal
from tests.named_types.sema_oracle import assert_conforms

EXAMPLE = {
    "BidderAlias": "hw1.isone.me.versant.keene.oak.ltn",
    "StartUnixS": 1794402000,
    "Reason": "BuildLost",
    "Detail": "worker killed by signal 9",
    "CreatedMs": 1794399946000,
    "TypeName": "flo.refusal",
    "Version": "000",
}


def example() -> dict:
    return copy.deepcopy(EXAMPLE)


def test_example_conforms() -> None:
    refusal = FloRefusal.model_validate(example())
    assert refusal.Reason == FloRefusalReason.BuildLost
    assert_conforms(refusal)


def test_no_detail_conforms() -> None:
    d = example()
    del d["Detail"]
    refusal = FloRefusal.model_validate(d)
    assert refusal.Detail is None
    assert "Detail" not in refusal.model_dump(by_alias=True, exclude_none=True)
    assert_conforms(refusal)


def test_an_unknown_reason_decodes_to_the_default() -> None:
    d = example()
    d["Reason"] = "SolverOnFire"
    assert FloRefusal.model_validate(d).Reason == FloRefusalReason.Unknown
