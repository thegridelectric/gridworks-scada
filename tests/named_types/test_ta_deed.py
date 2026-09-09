"""Tests ta.deed type, version 000"""

import pytest
from gwsproto.enums import TaValidationState
from gwsproto.named_types import TaDeed


def test_ta_deed_generated() -> None:
    d = {
        "TaId": "7b1e6f2a-4c3d-4e5f-8a9b-0c1d2e3f4a5b",
        "TaAlias": "hw1.isone.me.versant.keene.beech.ta",
        "ValidationState": "ValidatedRealAssetAndGps",
        "ValidatorAlias": "hw1.validator.gridworks",
        "IssuedS": 1757300400,
        "TypeName": "ta.deed",
        "Version": "000",
    }

    d2 = TaDeed.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
    assert TaDeed.model_validate(d).ValidationState == TaValidationState.ValidatedRealAssetAndGps


def test_ta_deed_axiom_1() -> None:
    """Axiom 1 (SimulatedAssetNeverWorld): a simulated-asset deed on a
    world-universe alias is rejected."""
    d = {
        "TaId": "2f6a9c4e-1b2d-4a3c-9e8f-5d4c3b2a1f0e",
        "TaAlias": "w.isone.me.versant.keene.simbeech.ta",
        "ValidationState": "ValidatedSimulatedAsset",
        "ValidatorAlias": "w.validator.gridworks",
        "IssuedS": 1757300400,
        "TypeName": "ta.deed",
        "Version": "000",
    }
    with pytest.raises(ValueError, match="Axiom 1"):
        TaDeed.model_validate(d)
    TaDeed.model_validate({**d, "TaAlias": "d1.isone.me.versant.keene.simbeech.ta"})
