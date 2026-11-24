"""ha1.params 007: the twin agrees with the snapshot on the word's example
and refuses the axiom's violation."""

from gwsproto.named_types import Ha1Params
from tests.named_types.sema_oracle import assert_conforms, assert_refused

EXAMPLE = {
    "AlphaTimes10": 120,
    "BetaTimes100": -22,
    "GammaEx6": 0,
    "IntermediatePowerKw": 1.5,
    "IntermediateRswtF": 100,
    "DdPowerKw": 12,
    "DdRswtF": 160,
    "DdDeltaTF": 20,
    "HpMaxKwEl": 6.0,
    "MaxEwtF": 170,
    "LoadOverestimationPercent": 10,
    "CopIntercept": 2.96,
    "CopLwtMinusOatCoeff": -0.00628,
    "HpTurnOnMinutes": 12,
    "TypeName": "ha1.params",
    "Version": "007",
}


def test_example_conforms() -> None:
    assert_conforms(Ha1Params.model_validate(EXAMPLE))


def test_ha1_params_axiom_1_non_positive_cop_lift_coefficient() -> None:
    d = dict(EXAMPLE, CopLwtMinusOatCoeff=0.001)
    assert_refused(Ha1Params, d, match="Axiom 1 \\(NonPositiveCopLiftCoefficient\\)")
